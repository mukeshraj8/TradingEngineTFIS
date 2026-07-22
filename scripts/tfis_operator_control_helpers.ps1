function Resolve-TfisOperatorControlRoot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return Join-Path $RepoRoot "tmp\operator_controls"
}

function Get-TfisOperatorControlEventLogPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return Join-Path (Resolve-TfisOperatorControlRoot -RepoRoot $RepoRoot) "operator_control_events.jsonl"
}

function Get-TfisLatestOperatorControlEvent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $eventLogPath = Get-TfisOperatorControlEventLogPath -RepoRoot $RepoRoot
    if (-not (Test-Path $eventLogPath)) {
        return $null
    }
    $latest = $null
    foreach ($line in Get-Content -Path $eventLogPath -Encoding UTF8) {
        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }
        try {
            $latest = $line | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            continue
        }
    }
    return $latest
}

function Get-TfisGlobalPauseMarkerPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    return Join-Path (Resolve-TfisOperatorControlRoot -RepoRoot $RepoRoot) "global_pause.json"
}

function Get-TfisStrategyPauseMarkerPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$StrategyCode
    )

    $normalizedStrategyCode = $StrategyCode.Trim().ToUpperInvariant()
    if ([string]::IsNullOrWhiteSpace($normalizedStrategyCode)) {
        throw "StrategyCode must not be blank."
    }
    return Join-Path (Resolve-TfisOperatorControlRoot -RepoRoot $RepoRoot) "strategy_${normalizedStrategyCode}.pause.json"
}

function Set-TfisOperatorPauseMarker {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$StrategyCode,
        [string]$Reason = "manual_operator_pause"
    )

    $controlRoot = Resolve-TfisOperatorControlRoot -RepoRoot $RepoRoot
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    $markerPath = if ([string]::IsNullOrWhiteSpace($StrategyCode)) {
        Get-TfisGlobalPauseMarkerPath -RepoRoot $RepoRoot
    }
    else {
        Get-TfisStrategyPauseMarkerPath -RepoRoot $RepoRoot -StrategyCode $StrategyCode
    }
    $payload = [ordered]@{
        reason = $Reason
        strategy_code = if ([string]::IsNullOrWhiteSpace($StrategyCode)) { $null } else { $StrategyCode.Trim().ToUpperInvariant() }
        updated_at = (Get-Date).ToString("o")
        updated_by = $env:USERNAME
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $markerPath -Value $payload -Encoding UTF8
    Write-TfisOperatorControlEvent -RepoRoot $RepoRoot -Action "PAUSE" -StrategyCode $StrategyCode -Reason $Reason -MarkerPath $markerPath
    return $markerPath
}

function Clear-TfisOperatorPauseMarker {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$StrategyCode
    )

    $markerPath = if ([string]::IsNullOrWhiteSpace($StrategyCode)) {
        Get-TfisGlobalPauseMarkerPath -RepoRoot $RepoRoot
    }
    else {
        Get-TfisStrategyPauseMarkerPath -RepoRoot $RepoRoot -StrategyCode $StrategyCode
    }
    if (Test-Path $markerPath) {
        Remove-Item -LiteralPath $markerPath -Force
    }
    Write-TfisOperatorControlEvent -RepoRoot $RepoRoot -Action "RESUME" -StrategyCode $StrategyCode -MarkerPath $markerPath
    return $markerPath
}

function Write-TfisOperatorControlEvent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$Action,
        [string]$StrategyCode,
        [string]$Reason,
        [string]$MarkerPath
    )

    $controlRoot = Resolve-TfisOperatorControlRoot -RepoRoot $RepoRoot
    New-Item -ItemType Directory -Path $controlRoot -Force | Out-Null
    $eventLogPath = Get-TfisOperatorControlEventLogPath -RepoRoot $RepoRoot
    $normalizedStrategyCode = if ([string]::IsNullOrWhiteSpace($StrategyCode)) { $null } else { $StrategyCode.Trim().ToUpperInvariant() }
    $normalizedAction = $Action.Trim().ToUpperInvariant()
    $scope = if ($normalizedStrategyCode) { "STRATEGY" } else { "GLOBAL" }
    $payload = [ordered]@{
        action = $normalizedAction
        scope = $scope
        strategy_code = $normalizedStrategyCode
        reason = if ([string]::IsNullOrWhiteSpace($Reason)) { $null } else { $Reason.Trim() }
        actor = $env:USERNAME
        occurred_at = (Get-Date).ToString("o")
        marker_path = $MarkerPath
    } | ConvertTo-Json -Compress -Depth 4
    Add-Content -Path $eventLogPath -Value $payload -Encoding UTF8
}
