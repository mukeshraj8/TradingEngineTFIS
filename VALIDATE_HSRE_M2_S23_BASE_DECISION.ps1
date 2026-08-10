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

function Invoke-ExpectedFailureSignature {
    param(
        [string]$Name,
        [string[]]$Command,
        [string]$ExpectedSignature
    )

    Write-Host ""
    Write-Host "== $Name =="
    $output = & $Command[0] $Command[1..($Command.Length - 1)] 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    $text = $output -join "`n"
    if ($exitCode -eq 0) {
        throw "$Name unexpectedly passed; re-baseline before accepting Milestone 2."
    }
    if ($text -notmatch [regex]::Escape($ExpectedSignature)) {
        throw "$Name did not preserve expected signature: $ExpectedSignature"
    }
}

$python = ".\.venv\Scripts\python.exe"

Invoke-RequiredStep `
    -Name "syntax" `
    -Command @(
        $python, "-m", "py_compile",
        "src\tfis\backtest\hsre_s23_base_decision.py",
        "tests\unit\test_hsre_s23_base_decision.py",
        "tests\integration\test_hsre_s23_base_decision_real_data.py"
    )

Invoke-RequiredStep `
    -Name "focused HSRE M2 tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_s23_base_decision.py", "-q")

Invoke-RequiredStep `
    -Name "no-lookahead tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_s23_base_decision.py", "-q", "-k", "lookahead")

Invoke-RequiredStep `
    -Name "option-history insufficiency tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_s23_base_decision.py", "-q", "-k", "insufficient")

Invoke-RequiredStep `
    -Name "real January S23 base-decision discovery" `
    -Command @($python, "-m", "pytest", "tests\integration\test_hsre_s23_base_decision_real_data.py", "-q", "-s")

Invoke-RequiredStep `
    -Name "deterministic one-day packet tests" `
    -Command @($python, "-m", "pytest", "tests\unit\test_hsre_s23_base_decision.py", "-q", "-k", "deterministic")

Invoke-ExpectedFailureSignature `
    -Name "authoritative focused S23 regression signature" `
    -Command @(
        $python, "-m", "pytest",
        "tests\unit\test_strategy_folder_loader.py",
        "tests\unit\test_option_chain_selection.py",
        "tests\unit\test_s23_all_branches.py",
        "tests\unit\test_strategy_registry_enforcement.py",
        "-q"
    ) `
    -ExpectedSignature "4 failed, 32 passed"

Invoke-ExpectedFailureSignature `
    -Name "pre-existing historical baseline signature" `
    -Command @(
        $python, "-m", "pytest",
        "tests\unit\test_historical_runner.py",
        "tests\unit\test_option_chain_selection.py",
        "tests\integration\test_historical_backtest_monthly_status_mode.py",
        "tests\integration\test_historical_backtest_s23_recalculation_mode.py",
        "tests\integration\test_contract_specific_lifecycle_mode.py",
        "-q"
    ) `
    -ExpectedSignature "7 failed, 21 passed"

Write-Host ""
Write-Host "HSRE Milestone 2 validation passed; known S23 and historical signatures preserved."
