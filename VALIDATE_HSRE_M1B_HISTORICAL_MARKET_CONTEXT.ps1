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
        throw "$Name unexpectedly passed; re-baseline before accepting Milestone 1B."
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
        "src\tfis\backtest\hsre_market_context.py",
        "tests\unit\test_hsre_market_context.py",
        "tests\integration\test_hsre_market_context_real_data.py"
    )

Invoke-RequiredStep `
    -Name "focused HSRE M1B unit tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_market_context.py", "-q")

Invoke-RequiredStep `
    -Name "no-lookahead and partial-view tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_market_context.py", "-q", "-k", "partial or prior or provenance")

Invoke-RequiredStep `
    -Name "insufficient-lookback fail-closed tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_market_context.py", "-q", "-k", "insufficient or missing_previous_month or unknown_monthly")

Invoke-RequiredStep `
    -Name "deterministic packet hash tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_market_context.py", "-q", "-k", "deterministic")

Invoke-RequiredStep `
    -Name "real HSRE January context smoke" `
    -Command @($python, "-m", "pytest", "tests\integration\test_hsre_market_context_real_data.py", "-q", "-s")

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
Write-Host "HSRE Milestone 1B validation passed; known historical baseline signature preserved."
