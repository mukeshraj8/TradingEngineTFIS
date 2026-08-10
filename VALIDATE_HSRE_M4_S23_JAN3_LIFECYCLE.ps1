param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"

function Run-Step {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed: $Name"
    }
}

function Run-ExpectedFailureStep {
    param(
        [string]$Name,
        [scriptblock]$Command,
        [string]$ExpectedSummary
    )
    Write-Host "== $Name =="
    $output = & $Command 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -eq 0) {
        throw "Step unexpectedly passed: $Name"
    }
    if (($output -join "`n") -notmatch [regex]::Escape($ExpectedSummary)) {
        throw "Step did not contain expected summary '$ExpectedSummary': $Name"
    }
}

Run-Step "syntax" {
    & $Python -m py_compile `
        src\tfis\backtest\hsre_s23_trade_lifecycle.py `
        tests\unit\test_hsre_s23_trade_lifecycle.py `
        tests\integration\test_hsre_s23_trade_lifecycle_real_data.py
}

Run-Step "focused lifecycle, chronology, same-bar ambiguity, and no-lookahead tests" {
    & $Python -m pytest tests\unit\test_hsre_s23_trade_lifecycle.py -q
}

Run-Step "actual Jan-3 end-to-end historical trade and deterministic hash" {
    & $Python -m pytest tests\integration\test_hsre_s23_trade_lifecycle_real_data.py -q -s
}

Run-Step "M3 final-order regression" {
    & $Python -m pytest `
        tests\unit\test_hsre_s23_final_order_decision.py `
        tests\integration\test_hsre_s23_final_order_decision_real_data.py `
        -q
}

Run-Step "48-pass authority regression" {
    & $Python -m pytest `
        tests\integration\test_compare_paper_to_historical_cli.py `
        tests\unit\test_s23_paper_vs_historical.py `
        tests\unit\test_s23_entry_missed.py `
        tests\unit\test_s23_recalculation.py `
        tests\unit\test_s23_live_decision_builder.py `
        -q
}

Run-ExpectedFailureStep "historical 21/7 baseline" {
    & $Python -m pytest `
        tests\unit\test_historical_runner.py `
        tests\unit\test_option_chain_selection.py `
        tests\integration\test_historical_backtest_monthly_status_mode.py `
        tests\integration\test_historical_backtest_s23_recalculation_mode.py `
        tests\integration\test_contract_specific_lifecycle_mode.py `
        -q
} "7 failed, 21 passed"

Run-ExpectedFailureStep "focused S23 32/4 baseline" {
    & $Python -m pytest `
        tests\unit\test_strategy_folder_loader.py `
        tests\unit\test_option_chain_selection.py `
        tests\unit\test_s23_all_branches.py `
        tests\unit\test_strategy_registry_enforcement.py `
        -q
} "4 failed, 32 passed"

Write-Host "HSRE M4 validation completed."
