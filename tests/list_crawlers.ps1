$h = @{"Authorization" = "Token 7b360643d08ed3ef041c81daeaac37a63ae2b0d5"}
$r = Invoke-RestMethod -Uri "https://api.lobstr.io/v1/crawlers" -Headers $h -UseBasicParsing
foreach ($c in $r.data) {
    $hasAcct = ($c.account -ne $null)
    Write-Host "$($c.slug) | $($c.name) | account_required:$hasAcct | cost:$($c.credits_per_row)"
}