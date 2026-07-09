param(
    [string]$TaskName = "TFIS S23 Morning Supervised Decision"
)

$task = $null
try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
} catch {
    $taskLookupError = $_.Exception.Message
}

if ($task) {
    $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
    $task | Format-List TaskName, TaskPath, State
    if ($info) {
        $info | Format-List LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
    }
    exit 0
}

$schtasksExe = Join-Path $env:SystemRoot "System32\schtasks.exe"
if (-not (Test-Path -LiteralPath $schtasksExe)) {
    Write-Host "Unable to query scheduled tasks."
    if ($taskLookupError) {
        Write-Host "Get-ScheduledTask lookup failed: $taskLookupError"
    }
    Write-Host "schtasks.exe not found at $schtasksExe"
    exit 1
}

$rows = & $schtasksExe /Query /V /FO CSV 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Unable to query scheduled tasks."
    if ($taskLookupError) {
        Write-Host "Get-ScheduledTask lookup failed: $taskLookupError"
    }
    Write-Host $rows
    exit $LASTEXITCODE
}

$expectedTaskNames = @($TaskName)
if (-not $TaskName.StartsWith("\")) {
    $expectedTaskNames += "\" + $TaskName
}

$matches = $rows | ConvertFrom-Csv | Where-Object {
    $expectedTaskNames -contains $_.TaskName
}

if (-not $matches) {
    Write-Host "Task not found: $TaskName"
    exit 1
}

$matches | Format-List
