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

function New-TfisPathRegex {
    param([string]$PathText)

    $fullPath = [System.IO.Path]::GetFullPath($PathText)
    $segments = @($fullPath -split '[\\/]+') | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    if ($segments.Count -eq 0) {
        return [Regex]::Escape($fullPath)
    }
    return ($segments | ForEach-Object { [Regex]::Escape($_) }) -join '[\\/]+'
}

function Get-TfisProcessCandidates {
    $nameFilter = "Name = 'python.exe' OR Name = 'pythonw.exe' OR Name = 'py.exe' OR Name = 'powershell.exe' OR Name = 'pwsh.exe'"
    return @(
        Get-CimInstance Win32_Process -Filter $nameFilter -ErrorAction SilentlyContinue
    )
}

function Get-TfisPortOwnerProcesses {
    param([int]$Port)

    $ownerProcessIds = @()
    $connections = @(
        Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    )
    if ($connections.Count -eq 0) {
        $connections = @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        )
    }
    $ownerProcessIds += @(
        $connections |
        Select-Object -ExpandProperty OwningProcess -ErrorAction SilentlyContinue |
        Where-Object { $_ -and $_ -gt 0 } |
        ForEach-Object { [int]$_ }
    )
    if ($ownerProcessIds.Count -eq 0) {
        $netstatLines = @(& netstat.exe -ano 2>$null | Select-String -Pattern (":$Port\s+.*\s+LISTENING\s+\d+\s*$"))
        foreach ($line in $netstatLines) {
            $text = [string]$line
            if ($text -match "^\s*TCP\s+\S+:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$") {
                $ownerProcessIds += [int]$Matches[1]
            }
        }
    }
    $ownerProcessIds = @($ownerProcessIds | Where-Object { $_ -and $_ -gt 0 } | Sort-Object -Unique)
    if ($ownerProcessIds.Count -eq 0) {
        return @()
    }
    $ownerProcesses = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $ownerProcessIds -contains $_.ProcessId } |
        Sort-Object ProcessId
    )
    if ($ownerProcesses.Count -gt 0) {
        return $ownerProcesses
    }
    return @(
        $ownerProcessIds |
        ForEach-Object {
            $processId = [int]$_
            $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
            if ($process) {
                [PSCustomObject]@{
                    ProcessId = $process.Id
                    Name = $process.ProcessName
                    CommandLine = $null
                    ParentProcessId = $null
                }
            }
        } |
        Sort-Object ProcessId
    )
}

function Get-TfisRuntimeProcessRole {
    param([string]$CommandLine)

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return "unknown"
    }
    if ($CommandLine -match "serve_operator_dashboard\.py") {
        return "dashboard"
    }
    if ($CommandLine -match "run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1") {
        return "supervisor"
    }
    if ($CommandLine -match "run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py|start_s21_fyers_morning_supervised_decision\.ps1|start_s23_fyers_morning_supervised_decision\.ps1") {
        return "morning_strategy"
    }
    if ($CommandLine -match "run_s23_paper_position_watch\.py|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1") {
        return "position_watcher"
    }
    if ($CommandLine -match "build_operator_dashboard\.py|refresh_tfis_operator_dashboard\.ps1") {
        return "dashboard_maintenance"
    }
    if ($CommandLine -match "reset_tfis_dashboard_and_watchers\.ps1") {
        return "runtime_startup"
    }
    if ($CommandLine -match "stop_tfis_runtime\.ps1") {
        return "runtime_stop"
    }
    return "other"
}

function Get-TfisRuntimeProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$RuntimePattern
    )

    $repoPattern = New-TfisPathRegex -PathText $RepoRoot
    $effectivePattern = if ([string]::IsNullOrWhiteSpace($RuntimePattern)) {
        'build_operator_dashboard\.py|serve_operator_dashboard\.py|refresh_tfis_operator_dashboard\.ps1|reset_tfis_dashboard_and_watchers\.ps1|run_s23_paper_position_watch\.py|run_tfis_paper_lifecycle_supervisor\.py|start_tfis_paper_lifecycle_supervisor\.ps1|start_s21_paper_watchers_from_metadata\.ps1|start_s23_paper_watchers_from_metadata\.ps1|run_s21_banknifty_0916_supervised_decision\.py|run_s23_fyers_0916_supervised_decision\.py|start_s21_fyers_morning_supervised_decision\.ps1|start_s23_fyers_morning_supervised_decision\.ps1|stop_tfis_runtime\.ps1'
    }
    else {
        $RuntimePattern
    }

    $candidates = @(Get-TfisProcessCandidates)
    $directMatches = @(
        $candidates |
        Where-Object {
            $cmd = $_.CommandLine
            if (-not $cmd) {
                return $false
            }
            if ($cmd -notmatch $repoPattern) {
                return $false
            }
            return $cmd -match $effectivePattern
        }
    )
    $matchedById = @{}
    foreach ($proc in $directMatches) {
        $matchedById[[int]$proc.ProcessId] = $proc
    }

    $changed = $true
    while ($changed) {
        $changed = $false
        foreach ($proc in $candidates) {
            $processId = [int]$proc.ProcessId
            if ($matchedById.ContainsKey($processId)) {
                continue
            }
            $parentProcessId = [int]$proc.ParentProcessId
            if ($matchedById.ContainsKey($parentProcessId)) {
                $matchedById[$processId] = $proc
                $changed = $true
            }
        }
    }

    return @($matchedById.Values | Sort-Object ProcessId)
}

function Get-TfisLogicalRuntimeProcesses {
    param(
        [object[]]$Processes = @()
    )

    if ($Processes.Count -eq 0) {
        return @()
    }

    $processesById = @{}
    foreach ($proc in $Processes) {
        $processesById[[int]$proc.ProcessId] = $proc
    }

    $componentByRoot = @{}
    foreach ($proc in @($Processes | Sort-Object ProcessId)) {
        $processId = [int]$proc.ProcessId
        $role = Get-TfisRuntimeProcessRole -CommandLine $proc.CommandLine
        $componentRootId = $processId
        $parentProcessId = [int]$proc.ParentProcessId
        while ($processesById.ContainsKey($parentProcessId)) {
            $parent = $processesById[$parentProcessId]
            $parentRole = Get-TfisRuntimeProcessRole -CommandLine $parent.CommandLine
            if ($parentRole -eq $role) {
                $componentRootId = [int]$parent.ProcessId
                $parentProcessId = [int]$parent.ParentProcessId
                continue
            }
            break
        }

        if (-not $componentByRoot.ContainsKey($componentRootId)) {
            $rootProc = $processesById[$componentRootId]
            $componentByRoot[$componentRootId] = [PSCustomObject]@{
                ProcessId = [int]$rootProc.ProcessId
                ProcessIds = @()
                Name = $rootProc.Name
                Role = Get-TfisRuntimeProcessRole -CommandLine $rootProc.CommandLine
                CommandLine = $rootProc.CommandLine
            }
        }
        $component = $componentByRoot[$componentRootId]
        $component.ProcessIds = @($component.ProcessIds + $processId | Sort-Object -Unique)
    }

    return @($componentByRoot.Values | Sort-Object ProcessId)
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
