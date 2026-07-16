param(
    [datetime]$Date = (Get-Date),
    [string]$TfisRoot,
    [string]$Config = "config/paper.s21.fyers_connect_test.yaml",
    [string[]]$StrategyPath = @(
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_CALL",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BULL_PUT",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_CALL",
        "config/strategies/options_sell/banknifty/S21_BANKNIFTY_OP_SELL_MONTHLY_BEAR_PUT"
    ),
    [string]$ReferencePacket = "config/reference_packets/s21_banknifty_monthly_live_decision_reference.json",
    [string]$ArtifactRoot = "data/strategies/S21/fyers_morning_supervised_decision",
    [string]$SessionIdPrefix = "s21-fyers-morning-supervised-decision",
    [string]$Timezone = "Asia/Kolkata",
    [ValidateSet("run_now", "abort")]
    [string]$IfPast = "run_now",
    [switch]$SkipRefresh,
    [switch]$EnableSmokeOverride,
    [string]$CarryForwardStateDir,
    [string]$TradingHolidayCalendar = "config/nse_trading_holidays_2026.json"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$paperPositionHelperPath = Join-Path $scriptDir "tfis_paper_position_state_helpers.ps1"
. $paperPositionHelperPath
if (-not $TfisRoot) {
    $TfisRoot = $repoRoot
}

$Host.UI.RawUI.WindowTitle = "TFIS S21 Morning Supervised Decision"

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Missing python executable: $pythonExe"
}

function Resolve-TfisAbsolutePathText {
    param([string]$PathText)

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $repoRoot $PathText))
}

function Resolve-TfisPositionStateDirectory {
    param([string]$PathText)

    $resolved = Resolve-TfisAbsolutePathText -PathText $PathText
    if (-not $resolved) {
        return $null
    }
    if ((Test-Path $resolved) -and -not (Get-Item $resolved).PSIsContainer) {
        return [System.IO.Path]::GetDirectoryName($resolved)
    }
    return $resolved
}

function Get-TfisOpenPositionStatePaths {
    param([datetime]$EffectiveDate)

    $artifactRootPath = Resolve-TfisAbsolutePathText -PathText $ArtifactRoot
    if (-not (Test-Path $artifactRootPath)) {
        return @()
    }

    return @(
        Get-ChildItem -Path $artifactRootPath -Recurse -Filter "paper_position_state.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            try {
                $stateJson = Get-Content -Path $_.FullName -Raw | ConvertFrom-Json
            }
            catch {
                return
            }

            if (-not (Test-TfisResumablePaperPositionStateJson -StateJson $stateJson -EffectiveDate $EffectiveDate)) {
                return
            }
            $_.FullName
        } |
        Select-Object -Unique
    )
}

function Test-TfisTradingHoliday {
    param(
        [datetime]$EffectiveDate,
        [string]$CalendarPath
    )

    $resolvedCalendar = Resolve-TfisAbsolutePathText -PathText $CalendarPath
    if (-not $resolvedCalendar -or -not (Test-Path $resolvedCalendar)) {
        return $false
    }

    try {
        $holidayJson = Get-Content -Path $resolvedCalendar -Raw | ConvertFrom-Json
    }
    catch {
        return $false
    }

    foreach ($entry in @($holidayJson.holidays)) {
        $dateText = [string]$entry.date
        if ($dateText -and $dateText -eq $EffectiveDate.ToString("yyyy-MM-dd")) {
            return $true
        }
    }
    return $false
}

if (Test-TfisTradingHoliday -EffectiveDate $Date -CalendarPath $TradingHolidayCalendar) {
    Write-Host "Skipping S21 supervised decision because $($Date.ToString('yyyy-MM-dd')) is configured as a trading holiday."
    exit 0
}

$logDir = Join-Path $repoRoot "tmp\s21_fyers_morning_supervised_decision\_task_launch_logs"
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmssfff_$PID"
$pythonOutputPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$stamp.out.log"
$pythonErrorPath = Join-Path $logDir "run_s21_banknifty_0916_supervised_decision_$stamp.err.log"
$launchLogPath = Join-Path $logDir "start_s21_fyers_morning_supervised_decision_$stamp.log"

function Write-LaunchLog {
    param([string]$Message)

    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz"), $Message
    Add-Content -Path $launchLogPath -Value $line -Encoding UTF8
    Write-Host $line
}

$effectiveRunDate = $Date.Date
$carryForwardStateDirArg = Resolve-TfisPositionStateDirectory -PathText $CarryForwardStateDir
if (-not $carryForwardStateDirArg) {
    $discoveredCarryForwardStatePaths = @(Get-TfisOpenPositionStatePaths -EffectiveDate $effectiveRunDate)
    if ($discoveredCarryForwardStatePaths.Count -gt 0) {
        $discoveredCarryForwardStatePath = Resolve-TfisAbsolutePathText -PathText ([string]$discoveredCarryForwardStatePaths[0])
        $carryForwardStateDirArg = Resolve-TfisPositionStateDirectory -PathText $discoveredCarryForwardStatePath
        Write-LaunchLog "Passing latest discovered open S21 paper position to supervised decision: $discoveredCarryForwardStatePath"
    }
}
elseif ($carryForwardStateDirArg) {
    Write-LaunchLog "Carry-forward state directory argument: $carryForwardStateDirArg"
}

$args = @(
    (Resolve-TfisAbsolutePathText -PathText "scripts/run_s21_banknifty_0916_supervised_decision.py"),
    "--tfis-root", $TfisRoot,
    "--config", (Resolve-TfisAbsolutePathText -PathText $Config),
    "--reference-packet", (Resolve-TfisAbsolutePathText -PathText $ReferencePacket),
    "--artifact-root", (Resolve-TfisAbsolutePathText -PathText $ArtifactRoot),
    "--session-id-prefix", $SessionIdPrefix,
    "--timezone", $Timezone,
    "--if-past", $IfPast
)

foreach ($strategy in $StrategyPath) {
    $args += "--strategy-path"
    $args += (Resolve-TfisAbsolutePathText -PathText $strategy)
}

if ($SkipRefresh) {
    $args += "--skip-refresh"
}
if ($EnableSmokeOverride) {
    $args += "--enable-smoke-override"
}
if ($carryForwardStateDirArg) {
    $args += "--carry-forward-state-dir"
    $args += $carryForwardStateDirArg
}

Write-LaunchLog "Starting S21 supervised decision Python process."
$process = Start-Process `
    -FilePath $pythonExe `
    -ArgumentList $args `
    -WorkingDirectory $repoRoot `
    -RedirectStandardOutput $pythonOutputPath `
    -RedirectStandardError $pythonErrorPath `
    -Wait `
    -PassThru `
    -WindowStyle Hidden
$exitCode = $process.ExitCode
Write-LaunchLog "Morning supervised decision finished with exit code $exitCode."

if ($exitCode -ne 0) {
    if (Test-Path $pythonErrorPath) {
        Get-Content -Path $pythonErrorPath | ForEach-Object { Write-Host $_ }
    }
    exit $exitCode
}

if (Test-Path $pythonOutputPath) {
    Get-Content -Path $pythonOutputPath | ForEach-Object { Write-Host $_ }
}

exit 0
