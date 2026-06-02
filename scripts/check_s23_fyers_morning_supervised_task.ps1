param(
    [string]$TaskName = "TFIS S23 Morning Supervised Decision"
)

$rows = schtasks /Query /V /FO CSV 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Unable to query scheduled tasks."
    Write-Host $rows
    exit $LASTEXITCODE
}

$matches = $rows | ConvertFrom-Csv | Where-Object {
    $_.TaskName -eq "\$TaskName"
}

if (-not $matches) {
    Write-Host "Task not found: $TaskName"
    exit 1
}

$matches | Format-List
