param(
    [string]$TfisRoot,
    [string]$Config = "config/paper.s23.fyers_connect_test.yaml",
    [string[]]$StrategyPath = @(
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL",
        "config/strategies/options_sell/nifty/S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT"
    ),
    [string]$ReferencePacket = "config/reference_packets/s23_bear_put_live_decision_reference.json",
    [string]$ArtifactRoot = "data/strategies/S23/fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s23-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "run_now",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir,
    [switch]$DisablePositionWatch,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json",
    [datetime]$RunDate
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$paperPositionHelperPath = Join-Path $scriptDir "tfis_paper_position_state_helpers.ps1"
$supervisorHelperPath = Join-Path $scriptDir "tfis_paper_lifecycle_supervisor_helpers.ps1"
$tradingCalendarHelperPath = Join-Path $scriptDir "tfis_trading_calendar_helpers.ps1"
$wrapperTaskHelperPath = Join-Path $scriptDir "tfis_wrapper_task_helpers.ps1"
. $paperPositionHelperPath
. $supervisorHelperPath
. $tradingCalendarHelperPath
. $wrapperTaskHelperPath
$Host.UI.RawUI.WindowTitle = "TFIS S23 Morning Supervised Decision"
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

Remove-Item Env:HTTP_PROXY,Env:HTTPS_PROXY,Env:http_proxy,Env:https_proxy,Env:ALL_PROXY,Env:all_proxy -ErrorAction SilentlyContinue

$taskContext = New-TfisTaskLaunchContext `
    -RepoRoot $repoRoot `
    -RelativeLogDirectory "tmp\s23_fyers_morning_supervised_decision\_task_launch_logs" `
    -LogFilePrefix "start_s23_fyers_morning_supervised_decision"
$logDir = $taskContext.LogDirectory
$stamp = $taskContext.Stamp
$logPath = $taskContext.LogPath

function Write-LaunchLog {
    param([string]$Message)
    Write-TfisTaskLogMessage -LogPath $logPath -Message $Message -ConsolePrefix "[TFIS S23] "
}

function Invoke-S23SupervisedDecisionProcess {
    param(
        [Parameter(Mandatory = $true)]
        [object[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$StdoutPath,
        [Parameter(Mandatory = $true)]
        [string]$StderrPath
    )

    $process = Start-TfisHiddenPythonProcess `
        -PythonExecutable $pythonExe `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $repoRoot `
        -StdoutPath $StdoutPath `
        -StderrPath $StderrPath

    $stdoutLines = @()
    $stderrLines = @()
    if (Test-Path $StdoutPath) {
        $stdoutLines = @(Get-Content -Path $StdoutPath)
    }
    if (Test-Path $StderrPath) {
        $stderrLines = @(Get-Content -Path $StderrPath)
    }

    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        StdoutLines = $stdoutLines
        StderrLines = $stderrLines
    }
}

function Get-TfisLatestSessionMetadata {
    param([datetime]$Date)

    $artifactRootPath = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $ArtifactRoot
    $metadataFile = Get-TfisLatestSessionMetadataFile -ArtifactRoot $artifactRootPath -SessionDate $Date
    if (-not $metadataFile) {
        $dayRoot = Join-Path $artifactRootPath $Date.ToString("yyyy-MM-dd")
        Write-LaunchLog "No TFIS S23 artifact day directory found for supervisor startup: $dayRoot"
        return $null
    }
    return $metadataFile
}

function Get-TfisOpenPositionStatePaths {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$Date
    )

    $artifactRootPath = $ArtifactRoot
    if (-not [System.IO.Path]::IsPathRooted($artifactRootPath)) {
        $artifactRootPath = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText $artifactRootPath
    }
    if (-not (Test-Path $artifactRootPath)) {
        Write-LaunchLog "No TFIS S23 artifact root found for open-position discovery: $artifactRootPath"
        return @()
    }

    return @(
        Get-TfisResumablePaperPositionStatePaths `
            -ArtifactRoot $artifactRootPath `
            -EffectiveDate $Date
    )
}

function Start-TfisSharedSupervisor {
    param(
        [Parameter(Mandatory = $true)]
        [datetime]$SessionDate,
        [Parameter(Mandatory = $true)]
        [string]$Reason
    )

    Write-LaunchLog $Reason
    $supervisorProcess = Start-TfisPaperLifecycleSupervisorProcess `
        -RepoRoot $repoRoot `
        -TfisRoot $TfisRoot `
        -SessionDate $SessionDate `
        -DisableDashboardRebuild:$DisableDashboardRebuild
    Write-LaunchLog "Started shared TFIS paper lifecycle supervisor PID=$($supervisorProcess.Id)."
}

$pythonExe = Resolve-TfisPythonExecutable -RepoRoot $repoRoot -AllowSystemPythonFallback

if ($PSBoundParameters.ContainsKey("RunDate")) {
    $effectiveRunDate = Get-TfisEffectiveRunDate -RunDate $RunDate
}
else {
    $effectiveRunDate = Get-TfisEffectiveRunDate
}

$args = @(
    (Join-Path $repoRoot "scripts\run_s23_fyers_0916_supervised_decision.py"),
    "--tfis-root", $TfisRoot,
    "--config", $Config,
    "--reference-packet", $ReferencePacket,
    "--artifact-root", $ArtifactRoot,
    "--session-id-prefix", $SessionIdPrefix,
    "--timezone", $Timezone,
    "--if-past", $IfPast
)

foreach ($strategy in $StrategyPath) {
    if ($strategy) {
        $args += "--strategy-path"
        $args += $strategy
    }
}

if ($SkipRefresh) {
    $args += "--skip-refresh"
}
if ($EnableSmokeOverride) {
    $args += "--enable-smoke-override"
}
if ($CarryForwardStateDir) {
    $carryForwardStateDirArg = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $CarryForwardStateDir
    $args += "--carry-forward-state-dir"
    $args += $carryForwardStateDirArg
    Write-LaunchLog "Using explicit S23 carry-forward state directory: $carryForwardStateDirArg"
}
else {
    $discoveredCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)
    if ($discoveredCarryForwardStatePaths.Count -gt 0) {
        $discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -RepoRoot $repoRoot -PathText ([string]$discoveredCarryForwardStatePaths[0])
        $discoveredCarryForwardStateDir = Resolve-TfisPositionStateDirectoryPath -RepoRoot $repoRoot -PathText $discoveredCarryForwardStatePath
        $args += "--carry-forward-state-dir"
        $args += $discoveredCarryForwardStateDir
        Write-LaunchLog "Passing latest discovered open S23 paper position to supervised decision: $discoveredCarryForwardStatePath"
        Write-LaunchLog "Carry-forward state directory argument: $discoveredCarryForwardStateDir"
    }
}

Show-TfisTaskBanner `
    -Title "TFIS S23 MORNING SUPERVISED DECISION" `
    -RepoRoot $repoRoot `
    -LogPath $logPath
Write-LaunchLog "Starting TFIS S23 morning supervised decision wrapper."
Write-LaunchLog "Python executable: $pythonExe"
Write-LaunchLog "TfisRoot: $TfisRoot"
Write-LaunchLog "ArtifactRoot: $ArtifactRoot"
Write-LaunchLog "SessionIdPrefix: $SessionIdPrefix"

$noRunReason = Get-TfisNoRunReason -RepoRoot $repoRoot -EffectiveDate $effectiveRunDate -CalendarPath $TradingHolidayCalendar
if ($noRunReason) {
    Write-LaunchLog $noRunReason
    Write-LaunchLog "Skipping TFIS S23 morning decision and supervisor startup."
    Write-LaunchLog "Wrapper finished with exit code 0."
    exit 0
}

try {
    $marketClosedNoAction = $false
    $pythonOutputPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$stamp.out.log"
    $pythonErrorPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$stamp.err.log"
    Write-LaunchLog "Supervised decision stdout: $pythonOutputPath"
    Write-LaunchLog "Supervised decision stderr: $pythonErrorPath"
    Write-LaunchLog "Starting supervised decision Python process."
    $result = Invoke-S23SupervisedDecisionProcess `
        -ArgumentList $args `
        -StdoutPath $pythonOutputPath `
        -StderrPath $pythonErrorPath
    $exitCode = $result.ExitCode
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    $stdoutLines = $result.StdoutLines
    $stderrLines = $result.StderrLines
    $stdoutLines | ForEach-Object {
        Write-LaunchLog ("PYTHON: {0}" -f $_)
        if ($_ -match "MARKET_CLOSED_NO_ACTION") {
            $marketClosedNoAction = $true
        }
    }
    $stderrLines | ForEach-Object {
        Write-LaunchLog ("PYTHON_ERR: {0}" -f $_)
        if ($_ -match "MARKET_CLOSED_NO_ACTION") {
            $marketClosedNoAction = $true
        }
    }

    $tokenRaceDetected = (
        (-not $SkipRefresh) -and
        ($exitCode -ne 0) -and
        ($stderrLines -match "invalid auth code").Count -gt 0
    )
    if ($tokenRaceDetected) {
        Write-LaunchLog "Detected FYERS auth-code race during S23 refresh; retrying once with --skip-refresh."
        $retryStamp = "{0}_retry_skip_refresh" -f $stamp
        $retryOutputPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$retryStamp.out.log"
        $retryErrorPath = Join-Path $logDir "run_s23_fyers_0916_supervised_decision_$retryStamp.err.log"
        $retryArgs = @($args + "--skip-refresh")
        $retryResult = Invoke-S23SupervisedDecisionProcess `
            -ArgumentList $retryArgs `
            -StdoutPath $retryOutputPath `
            -StderrPath $retryErrorPath
        $exitCode = $retryResult.ExitCode
        if ($null -eq $exitCode) {
            $exitCode = 0
        }
        $stdoutLines = $retryResult.StdoutLines
        $stderrLines = $retryResult.StderrLines
        $marketClosedNoAction = $false
        $stdoutLines | ForEach-Object {
            Write-LaunchLog ("PYTHON_RETRY: {0}" -f $_)
            if ($_ -match "MARKET_CLOSED_NO_ACTION") {
                $marketClosedNoAction = $true
            }
        }
        $stderrLines | ForEach-Object {
            Write-LaunchLog ("PYTHON_RETRY_ERR: {0}" -f $_)
            if ($_ -match "MARKET_CLOSED_NO_ACTION") {
                $marketClosedNoAction = $true
            }
        }
        $pythonOutputPath = $retryOutputPath
        $pythonErrorPath = $retryErrorPath
    }
    Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."
    if ($marketClosedNoAction) {
        Write-LaunchLog "Market-closed/no-action result detected; skipping S23 paper supervisor startup."
    }
    if (($exitCode -eq 0) -and (-not $DisablePositionWatch) -and (-not $marketClosedNoAction)) {
        $metadata = Get-TfisLatestSessionMetadata -Date $effectiveRunDate
        if ($metadata) {
            Write-LaunchLog "Using S23 metadata for supervisor startup: $($metadata.FullName)"
            $metadataJson = Get-Content -Path $metadata.FullName -Raw | ConvertFrom-Json
            $statePaths = @()
            $orderPaths = @()
            $stateDirectories = @{}
            $openCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -Date $effectiveRunDate)
            if ($openCarryForwardStatePaths.Count -gt 0) {
                foreach ($openStatePath in $openCarryForwardStatePaths) {
                    $openStateDir = Split-Path -Parent ([string]$openStatePath)
                    if (-not $stateDirectories.ContainsKey($openStateDir)) {
                        $statePaths += [string]$openStatePath
                        $stateDirectories[$openStateDir] = $true
                    }
                }
                Write-LaunchLog "Discovered $($openCarryForwardStatePaths.Count) open/carry-forward S23 paper position state file(s) for supervisor startup."
            }
            if ($metadataJson.branch_position_state_json) {
                $metadataJson.branch_position_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $metadataStateDir = Split-Path -Parent ([string]$_.Value)
                        if (-not $stateDirectories.ContainsKey($metadataStateDir)) {
                            $statePaths += [string]$_.Value
                            $stateDirectories[$metadataStateDir] = $true
                        }
                    }
                }
            }
            if ($metadataJson.branch_order_state_json) {
                $metadataJson.branch_order_state_json.PSObject.Properties | ForEach-Object {
                    if ($_.Value) {
                        $orderDir = Split-Path -Parent ([string]$_.Value)
                        if (-not $stateDirectories.ContainsKey($orderDir)) {
                            $derivedStatePath = Join-Path $orderDir "paper_position_state.json"
                            if (Test-Path $derivedStatePath) {
                                $statePaths += $derivedStatePath
                                $stateDirectories[$orderDir] = $true
                            }
                            else {
                                $orderPaths += [string]$_.Value
                            }
                        }
                    }
                }
            }
            if (($statePaths.Count + $orderPaths.Count) -gt 0) {
                Start-TfisSharedSupervisor `
                    -SessionDate $effectiveRunDate `
                    -Reason "Starting shared TFIS paper lifecycle supervisor for discovered S23/S21 paper targets."
            }
            else {
                Start-TfisSharedSupervisor `
                    -SessionDate $effectiveRunDate `
                    -Reason "No new S23 paper position/order state was produced; starting shared TFIS lifecycle supervisor in discovery mode."
            }
        }
        else {
            Start-TfisSharedSupervisor `
                -SessionDate $effectiveRunDate `
                -Reason "No scheduled_run_metadata.json found for $($effectiveRunDate.ToString('yyyy-MM-dd')); starting shared TFIS lifecycle supervisor in discovery mode."
        }
    }
    elseif ($DisablePositionWatch) {
        Write-LaunchLog "Position watch disabled by switch."
    }
    Write-LaunchLog "Wrapper finished with exit code $exitCode."
    exit $exitCode
}
catch {
    Write-LaunchLog ("Wrapper failed: {0}" -f $_.Exception.Message)
    throw
}
