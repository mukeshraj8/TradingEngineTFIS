function New-TfisRegexAlternation {
    param([string[]]$Values)

    $parts = @()
    foreach ($value in $Values) {
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $parts += [Regex]::Escape($value)
        }
    }
    $parts = $parts | Select-Object -Unique
    if ($parts.Count -eq 0) {
        return ""
    }
    if ($parts.Count -eq 1) {
        return $parts[0]
    }
    return "(?:" + ($parts -join "|") + ")"
}

function Get-TfisProcessCandidates {
    $nameFilter = "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'powershell.exe' OR Name = 'pwsh.exe'"
    return @(
        Get-CimInstance Win32_Process -Filter $nameFilter -ErrorAction SilentlyContinue
    )
}

function Get-TfisRuntimeProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$RuntimePattern
    )

    $repoPattern = [Regex]::Escape($RepoRoot)
    $effectivePattern = if ([string]::IsNullOrWhiteSpace($RuntimePattern)) {
        'build_operator_dashboard\.py|serve_operator_dashboard\.py|run_s23_paper_position_watch\.py|run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1|run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py|stop_tfis_runtime\.ps1'
    }
    else {
        $RuntimePattern
    }
    return @(
        Get-TfisProcessCandidates |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) {
                return $false
            }
            if ($cmd -notmatch $repoPattern) {
                return $false
            }
            return $cmd -match $effectivePattern
        } |
        Sort-Object ProcessId
    )
}

function Wait-ForNoTfisRuntimeProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [int[]]$ProcessIds = @(),
        [int]$TimeoutSeconds = 12
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $remaining = @()
        if ($ProcessIds.Count -gt 0) {
            foreach ($processId in $ProcessIds | Select-Object -Unique) {
                try {
                    $null = Get-Process -Id $processId -ErrorAction Stop
                    $remaining += $processId
                }
                catch {
                    continue
                }
            }
        }
        else {
            $remaining = @(Get-TfisRuntimeProcesses -RepoRoot $RepoRoot | Select-Object -ExpandProperty ProcessId)
        }
        if ($remaining.Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 500
    }

    $remainingDetails = @(
        Get-TfisRuntimeProcesses -RepoRoot $RepoRoot | ForEach-Object {
            "PID=$($_.ProcessId)"
        }
    )
    throw "Timed out waiting for TFIS runtime processes to exit: $($remainingDetails -join ', ')"
}

function Stop-TfisProcessTree {
    param([int]$ProcessId)

    $taskkillExe = Join-Path $env:SystemRoot "System32\taskkill.exe"
    if (Test-Path $taskkillExe) {
        & $taskkillExe /PID $ProcessId /T /F 2>$null | Out-Null
        return
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction Stop
}

function Stop-TfisRuntimeProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [int]$CurrentProcessId = $PID
    )

    $processes = @(Get-TfisRuntimeProcesses -RepoRoot $RepoRoot)
    $targetProcessIds = @()

    foreach ($proc in $processes) {
        if ($proc.ProcessId -eq $CurrentProcessId) {
            continue
        }
        $targetProcessIds += $proc.ProcessId
        Write-Host "Stopping TFIS process PID=$($proc.ProcessId)"
        try {
            Stop-TfisProcessTree -ProcessId $proc.ProcessId
        }
        catch {
            Write-Host "TFIS process PID=$($proc.ProcessId) already exited"
        }
    }

    if ($targetProcessIds.Count -gt 0) {
        Wait-ForNoTfisRuntimeProcesses -RepoRoot $RepoRoot -ProcessIds $targetProcessIds
    }
}
