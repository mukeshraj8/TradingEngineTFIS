$ErrorActionPreference = "Stop"

function Invoke-RequiredStep {
    param(
        [string]$Name,
        [string[]]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    & $Command[0] $Command[1..($Command.Length - 1)]
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Invoke-BaselineStep {
    param(
        [string]$Name,
        [string[]]$Command
    )

    Write-Host ""
    Write-Host "== $Name =="
    $output = & $Command[0] $Command[1..($Command.Length - 1)] 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    $text = $output -join "`n"
    if ($exitCode -eq 0) {
        throw "$Name unexpectedly passed; re-baseline before accepting Milestone 1C."
    }
    if ($text -notmatch "7 failed, 21 passed") {
        throw "$Name did not preserve the known baseline signature: expected '7 failed, 21 passed'."
    }
}

$python = ".\.venv\Scripts\python.exe"

Invoke-RequiredStep `
    -Name "syntax" `
    -Command @(
        $python, "-m", "py_compile",
        "src\tfis\backtest\nifty_hsre_data_adapter.py",
        "src\tfis\backtest\hsre_option_references.py",
        "tests\unit\test_hsre_option_references.py",
        "tests\integration\test_hsre_option_references_real_data.py"
    )

Invoke-RequiredStep `
    -Name "focused HSRE M1C unit tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q")

Invoke-RequiredStep `
    -Name "identity-isolation tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q", "-k", "isolation or expiry_strike")

Invoke-RequiredStep `
    -Name "no-lookahead tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q", "-k", "exclude_current_day or future")

Invoke-RequiredStep `
    -Name "insufficient-history tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q", "-k", "insufficient")

Invoke-RequiredStep `
    -Name "real HistoricalData contract-history discovery" `
    -Command @($python, "-m", "pytest", "tests\integration\test_hsre_option_references_real_data.py", "-q", "-s")

Invoke-RequiredStep `
    -Name "deterministic hash tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q", "-k", "deterministic")

Invoke-RequiredStep `
    -Name "OptionLevelsSnapshot compatibility conversion tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_option_references.py", "-q", "-k", "converts or cannot_convert")

Invoke-BaselineStep `
    -Name "pre-existing historical baseline signature" `
    -Command @(
        $python, "-m", "pytest",
        "tests\unit\test_historical_runner.py",
        "tests\unit\test_option_chain_selection.py",
        "tests\integration\test_historical_backtest_monthly_status_mode.py",
        "tests\integration\test_historical_backtest_s23_recalculation_mode.py",
        "tests\integration\test_contract_specific_lifecycle_mode.py",
        "-q"
    )

Write-Host ""
Write-Host "HSRE Milestone 1C validation passed; known historical baseline signature preserved."
