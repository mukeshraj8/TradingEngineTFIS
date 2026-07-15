param(
    [string]$TaskName = "TFIS S21 Morning Supervised Decision"
)

$ErrorActionPreference = "Continue"

try {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $task | Format-List TaskName, TaskPath, State

    $info = Get-ScheduledTaskInfo -TaskName $TaskName -TaskPath $task.TaskPath -ErrorAction SilentlyContinue
    if ($info) {
        $info | Format-List LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
    }
}
catch {
    $taskLookupError = $_.Exception.Message
    Write-Host "Get-ScheduledTask lookup failed: $taskLookupError"
}

$schtasksExe = Join-Path $env:SystemRoot "System32\schtasks.exe"
if (Test-Path $schtasksExe) {
    Write-Host ""
    Write-Host "schtasks /Query fallback:"
    & $schtasksExe /Query /V /FO CSV 2>&1 |
        Select-String -Pattern $TaskName |
        ForEach-Object { $_.Line }
}
