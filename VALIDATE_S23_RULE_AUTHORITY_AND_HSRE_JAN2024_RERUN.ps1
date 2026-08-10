param(
    [string]$DataRoot = "D:\HistoricalData\Nifty",
    [string]$CorrectedDir = "reports\hsre\S23\2024-01-rule-corrected",
    [string]$DeterminismDir = "reports\hsre\S23\2024-01-rule-corrected_determinism_check",
    [string]$OldDir = "reports\hsre\S23\2024-01"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot
$env:PYTHONPATH = "src"
$python = ".\.venv\Scripts\python.exe"

function Invoke-Checked {
    param(
        [string]$Name,
        [scriptblock]$Command
    )
    Write-Host "== $Name =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

function Invoke-ExpectedPytestSignature {
    param(
        [string]$Name,
        [string[]]$TestArgs,
        [string]$ExpectedSummary,
        [string[]]$ExpectedFailures
    )
    Write-Host "== $Name =="
    $output = & $python -m pytest @TestArgs -q 2>&1
    $text = $output -join "`n"
    Write-Host $text
    if ($text -notmatch [regex]::Escape($ExpectedSummary)) {
        throw "$Name did not preserve expected summary '$ExpectedSummary'"
    }
    foreach ($failure in $ExpectedFailures) {
        if ($text -notmatch [regex]::Escape($failure)) {
            throw "$Name missing expected failing test '$failure'"
        }
    }
}

function Get-ReportHashes {
    param([string]$Dir)
    $names = @(
        "daily_decisions.csv",
        "trades.csv",
        "non_trades.csv",
        "rejected_candidates_summary.csv",
        "entry_distance.csv",
        "summary.json"
    )
    $result = [ordered]@{}
    foreach ($name in $names) {
        $path = Join-Path $Dir $name
        if (-not (Test-Path $path)) {
            throw "Missing report file: $path"
        }
        $result[$name] = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLowerInvariant()
    }
    return $result
}

Invoke-Checked "syntax" {
    & $python -m py_compile `
        src\tfis\market_metadata\lot_size.py `
        src\tfis\backtest\hsre_s23_base_decision.py `
        src\tfis\backtest\hsre_s23_final_order_decision.py `
        src\tfis\backtest\hsre_s23_month_run.py `
        scripts\compare_hsre_s23_january_rule_correction.py `
        scripts\run_hsre_s23_january_2024.py
}

Invoke-Checked "focused rule authority, lot-size, premium, OI, exact-history, ORPT tests" {
    & $python -m pytest `
        tests\unit\test_market_metadata_lot_size.py `
        tests\unit\test_strategy_folder_loader.py `
        tests\unit\test_hsre_s23_base_decision.py `
        tests\unit\test_hsre_option_references.py `
        tests\unit\test_s23_entry_missed.py `
        tests\unit\test_hsre_s23_final_order_decision.py `
        -q
}

Invoke-Checked "authority/paper parity suite" {
    & $python -m pytest `
        tests\integration\test_compare_paper_to_historical_cli.py `
        tests\unit\test_s23_paper_vs_historical.py `
        tests\unit\test_s23_entry_missed.py `
        tests\unit\test_s23_recalculation.py `
        tests\unit\test_s23_live_decision_builder.py `
        -q
}

Invoke-ExpectedPytestSignature `
    -Name "historical baseline expected signature" `
    -TestArgs @(
        "tests\unit\test_historical_runner.py",
        "tests\unit\test_option_chain_selection.py",
        "tests\integration\test_historical_backtest_monthly_status_mode.py",
        "tests\integration\test_historical_backtest_s23_recalculation_mode.py",
        "tests\integration\test_contract_specific_lifecycle_mode.py"
    ) `
    -ExpectedSummary "7 failed, 21 passed" `
    -ExpectedFailures @(
        "test_historical_monthly_status_mode_selects_bull_and_bear_branches",
        "test_historical_monthly_status_mode_option_chain_selection_reports_selected_contract",
        "test_default_historical_monthly_status_backtest_is_unchanged_without_flag",
        "test_recalculation_mode_uses_spot_intraday_csv_when_provided",
        "test_contract_specific_lifecycle_uses_selected_contract_series_when_available",
        "test_contract_specific_lifecycle_uses_added_put_contract_series_when_available",
        "test_contract_specific_lifecycle_achieves_full_fixture_coverage_without_fallback"
    )

Invoke-ExpectedPytestSignature `
    -Name "focused S23 expected signature" `
    -TestArgs @(
        "tests\unit\test_strategy_folder_loader.py",
        "tests\unit\test_option_chain_selection.py",
        "tests\unit\test_s23_all_branches.py",
        "tests\unit\test_strategy_registry_enforcement.py"
    ) `
    -ExpectedSummary "4 failed, 32 passed" `
    -ExpectedFailures @(
        "test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D]",
        "test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_CALL]",
        "test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BEAR_PUT]",
        "test_all_s23_branch_folders_evaluate_expected_sample_outputs[S23_NIFTY_OP_SELL_WK_DIFF_2D_3D_BULL_PUT]"
    )

Invoke-Checked "corrected January HSRE run" {
    & $python scripts\run_hsre_s23_january_2024.py --data-root $DataRoot --output-dir $CorrectedDir
}

Invoke-Checked "corrected January deterministic rerun" {
    & $python scripts\run_hsre_s23_january_2024.py --data-root $DataRoot --output-dir $DeterminismDir
}

$firstHashes = Get-ReportHashes -Dir $CorrectedDir
$secondHashes = Get-ReportHashes -Dir $DeterminismDir
foreach ($name in $firstHashes.Keys) {
    if ($firstHashes[$name] -ne $secondHashes[$name]) {
        throw "Determinism hash mismatch for ${name}: $($firstHashes[$name]) != $($secondHashes[$name])"
    }
}

Invoke-Checked "old-vs-corrected comparison report" {
    & $python scripts\compare_hsre_s23_january_rule_correction.py `
        --old-dir $OldDir `
        --new-dir $CorrectedDir `
        --output (Join-Path $CorrectedDir "before_after_rule_correction.md")
}

Write-Host "VALIDATION PASSED"
Write-Host ($firstHashes | ConvertTo-Json -Depth 4)
