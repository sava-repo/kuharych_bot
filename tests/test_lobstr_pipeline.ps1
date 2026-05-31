# ============================================================
# Test Lobstr Pipeline: Instagram Reels -> Caption
# ============================================================
param(
    [Parameter(Mandatory=$true)]
    [string]$Token,

    [string]$ReelUrl = "https://www.instagram.com/reel/DYP0xYVt77D/?igsh=MTJpejJhdGM1dTV3OQ=="
)

$ErrorActionPreference = "Stop"
$BaseUrl = "https://api.lobstr.io/v1"

function Call-Lobstr {
    param([string]$Method = "GET", [string]$Path, [string]$JsonBody = $null)

    $url = $BaseUrl + $Path
    $headers = @{
        "Authorization" = "Token $Token"
    }

    if ($Method -eq "GET") {
        $resp = Invoke-RestMethod -Uri $url -Method GET -Headers $headers -UseBasicParsing
        return $resp
    }

    $headers["Content-Type"] = "application/json"
    if ($JsonBody) {
        $resp = Invoke-RestMethod -Uri $url -Method $Method -Headers $headers -Body $JsonBody -UseBasicParsing
    } else {
        $resp = Invoke-RestMethod -Uri $url -Method $Method -Headers $headers -UseBasicParsing
    }
    return $resp
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  TEST LOBSTR PIPELINE: Instagram Reels" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 0: Auth check
Write-Host "[Step 0] Auth check..." -ForegroundColor Yellow
try {
    $me = Call-Lobstr -Path "/me"
    Write-Host "  OK: $($me.first_name) $($me.last_name) ($($me.email))" -ForegroundColor Green
} catch {
    Write-Host "  FAIL: Auth failed. Check token." -ForegroundColor Red
    exit 1
}

# Step 1: Balance
Write-Host ""
Write-Host "[Step 1] Balance..." -ForegroundColor Yellow
$bal = Call-Lobstr -Path "/user/balance"
$rem = $bal.available - $bal.consumed
Write-Host "  Plan: $($bal.name), Available: $($bal.available), Consumed: $($bal.consumed), Remaining: $rem" -ForegroundColor Green

# Step 2: Find Instagram crawler
Write-Host ""
Write-Host "[Step 2] Find Instagram crawler..." -ForegroundColor Yellow
$crawlers = Call-Lobstr -Path "/crawlers"
$instaCrawler = $null

foreach ($c in $crawlers.data) {
    if ($c.slug -like "*instagram*") {
        Write-Host "  Found: $($c.name) (slug: $($c.slug), id: $($c.id))" -ForegroundColor DarkGray
        if ($instaCrawler -eq $null) {
            $instaCrawler = $c
        }
    }
}

if ($instaCrawler -eq $null) {
    Write-Host "  FAIL: No Instagram crawler found!" -ForegroundColor Red
    Write-Host "  Available crawlers:" -ForegroundColor DarkGray
    foreach ($c in $crawlers.data) {
        Write-Host "    - $($c.slug): $($c.name)" -ForegroundColor DarkGray
    }
    exit 1
}

Write-Host "  Using: $($instaCrawler.name) [$($instaCrawler.id)]" -ForegroundColor Green
Write-Host "  Cost: $($instaCrawler.credits_per_row) credits/row" -ForegroundColor Green

# Check if account is required
if ($instaCrawler.account -ne $null) {
    Write-Host "  WARNING: This crawler requires an Instagram account!" -ForegroundColor Red
}

# Step 3: Create Squid
Write-Host ""
Write-Host "[Step 3] Create Squid..." -ForegroundColor Yellow
$squidJson = "{`"crawler`": `"$($instaCrawler.id)`", `"name`": `"Test Reel Pipeline`"}"
$squid = Call-Lobstr -Method "POST" -Path "/squids" -JsonBody $squidJson
$squidId = $squid.id
Write-Host "  OK: Squid created (id: $squidId)" -ForegroundColor Green

# Step 4: Get crawler params
Write-Host ""
Write-Host "[Step 4] Crawler params..." -ForegroundColor Yellow
try {
    $cparams = Call-Lobstr -Path "/crawlers/$($instaCrawler.id)/params"
    $cparams | ConvertTo-Json -Depth 3 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
} catch {
    Write-Host "  (no params endpoint)" -ForegroundColor DarkGray
}

# Step 5: Add task
Write-Host ""
Write-Host "[Step 5] Add task with Reel URL..." -ForegroundColor Yellow
Write-Host "  URL: $ReelUrl" -ForegroundColor DarkGray
$taskJson = "{`"squid`": `"$squidId`", `"tasks`": [{`"url`": `"$ReelUrl`"}]}"
$taskResult = Call-Lobstr -Method "POST" -Path "/tasks" -JsonBody $taskJson
Write-Host "  OK: Added $($taskResult.tasks.Count) tasks, duplicates: $($taskResult.duplicated_count)" -ForegroundColor Green

# Step 6: Start run
Write-Host ""
Write-Host "[Step 6] Start Run..." -ForegroundColor Yellow
$runJson = "{`"squid`": `"$squidId`"}"
$run = Call-Lobstr -Method "POST" -Path "/runs" -JsonBody $runJson
$runId = $run.id
Write-Host "  OK: Run started (id: $runId, status: $($run.status))" -ForegroundColor Green

# Step 7: Wait for completion
Write-Host ""
Write-Host "[Step 7] Waiting for completion..." -ForegroundColor Yellow
$done = $false
$attempts = 0

while (($done -eq $false) -and ($attempts -lt 60)) {
    $attempts++
    Start-Sleep -Seconds 5
    $rs = Call-Lobstr -Path "/runs/$runId"
    $st = $rs.status
    Write-Host "  [$attempts] Status: $st, Results: $($rs.total_results)" -ForegroundColor DarkGray

    if (($st -eq "done") -or ($st -eq "aborted") -or ($st -eq "error")) {
        $done = $true
        Write-Host ""
        Write-Host "  Run finished!" -ForegroundColor Green
        Write-Host "  Status: $st" -ForegroundColor $(if ($st -eq "done") {"Green"} else {"Red"})
        Write-Host "  Results: $($rs.total_results)" -ForegroundColor Green
        Write-Host "  Reason: $($rs.done_reason)" -ForegroundColor Green
        Write-Host "  Credits: $($rs.credit_used)" -ForegroundColor Green
        Write-Host "  Duration: $($rs.duration)" -ForegroundColor Green

        if ($st -eq "error") {
            Write-Host "  ERROR reason: $($rs.done_reason)" -ForegroundColor Red
            Write-Host "  ERROR desc: $($rs.done_reason_desc)" -ForegroundColor Red
        }
    }
}

if ($attempts -ge 60) {
    Write-Host "  TIMEOUT after 5 min" -ForegroundColor Red
}

# Step 8: Wait for export
if (($done -eq $true) -and ($rs.status -eq "done") -and ($rs.export_done -eq $false)) {
    Write-Host ""
    Write-Host "[Step 8] Waiting for export..." -ForegroundColor Yellow
    $exportDone = $false
    while ($exportDone -eq $false) {
        Start-Sleep -Seconds 3
        $rc = Call-Lobstr -Path "/runs/$runId"
        if ($rc.export_done -eq $true) {
            $exportDone = $true
            Write-Host "  Export ready" -ForegroundColor Green
        }
    }
}

# Step 9: Get results
Write-Host ""
Write-Host "[Step 9] Get results..." -ForegroundColor Yellow
try {
    $results = Call-Lobstr -Path "/results?squid=$squidId&limit=10&page=1"
    if (($results.data -ne $null) -and ($results.data.Count -gt 0)) {
        Write-Host "  Total results: $($results.total_results)" -ForegroundColor Green
        Write-Host ""
        Write-Host "  === RESULTS ===" -ForegroundColor Cyan
        foreach ($row in $results.data) {
            Write-Host ""
            Write-Host "  --- Result ---" -ForegroundColor Cyan
            foreach ($prop in $row.PSObject.Properties) {
                $v = $prop.Value
                if ($v -is [string] -and $v.Length -gt 300) {
                    $v = $v.Substring(0, 300) + "..."
                }
                Write-Host "    $($prop.Name): $v" -ForegroundColor White
            }
        }
    } else {
        Write-Host "  No results found" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Error getting results: $_" -ForegroundColor Red
}

# Step 10: Stats
Write-Host ""
Write-Host "[Step 10] Run stats..." -ForegroundColor Yellow
try {
    $stats = Call-Lobstr -Path "/runs/$runId/stats"
    Write-Host "  Progress: $($stats.percent_done)" -ForegroundColor Green
    Write-Host "  Tasks done: $($stats.total_tasks_done)/$($stats.total_tasks)" -ForegroundColor Green
} catch {
    Write-Host "  (stats not available)" -ForegroundColor DarkGray
}

# Cleanup
Write-Host ""
Write-Host "[Cleanup] Delete test Squid..." -ForegroundColor Yellow
try {
    Call-Lobstr -Method "DELETE" -Path "/squids/$squidId"
    Write-Host "  OK: Squid $squidId deleted" -ForegroundColor Green
} catch {
    Write-Host "  (cleanup skipped)" -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  TEST COMPLETE" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan