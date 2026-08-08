param(
    [string]$RepoRoot = "D:\TradingEngineTFIS",
    [string[]]$SessionDates = @(
        "2026-08-03",
        "2026-08-04",
        "2026-08-05",
        "2026-08-06",
        "2026-08-07"
    ),
    [string]$OutputRoot = "reports\s21_weekend_historical_certification"
)

$ErrorActionPreference = "Stop"
Set-Location $RepoRoot

function Write-Step([string]$Text) {
    Write-Host "`n==> $Text" -ForegroundColor Cyan
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$certRoot = Join-Path $RepoRoot $OutputRoot
$runRoot = Join-Path $certRoot $timestamp
New-Item -ItemType Directory -Force -Path $runRoot | Out-Null

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " TFIS S21 WEEKEND HISTORICAL CERTIFICATION HARNESS" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "Repository : $RepoRoot"
Write-Host "Run root   : $runRoot"
Write-Host "Dates      : $($SessionDates -join ', ')"
Write-Host ""
Write-Host "READ-ONLY / NO BROKER ORDERS" -ForegroundColor Green

# ------------------------------------------------------------
# 1. Repository and safety evidence
# ------------------------------------------------------------
Write-Step "Recording repository state and S23 non-regression guard"

git rev-parse HEAD | Out-File (Join-Path $runRoot "git_head.txt") -Encoding utf8
git status --short | Out-File (Join-Path $runRoot "git_status.txt") -Encoding utf8
git diff | Out-File (Join-Path $runRoot "git_diff.patch") -Encoding utf8

$guardTemp = Join-Path $RepoRoot ".pytest_tmp\s21_weekend_s23_guard"
Remove-Item -Recurse -Force $guardTemp -ErrorAction SilentlyContinue

& ".\.venv\Scripts\python.exe" -m pytest `
    tests\unit\test_s23_live_decision_builder.py `
    tests\unit\test_s23_live_decision_timeline.py `
    tests\unit\test_s23_paper_contract_selection.py `
    "--basetemp=$guardTemp" `
    -q *>&1 | Tee-Object -FilePath (Join-Path $runRoot "s23_non_regression_guard.txt")

$s23GuardExit = $LASTEXITCODE
if ($s23GuardExit -ne 0) {
    throw "S23 non-regression guard failed. Historical S21 certification aborted."
}

# ------------------------------------------------------------
# 2. S21 focused validation
# ------------------------------------------------------------
Write-Step "Running S21 focused validation"

$s21Temp = Join-Path $RepoRoot ".pytest_tmp\s21_weekend_rules"
Remove-Item -Recurse -Force $s21Temp -ErrorAction SilentlyContinue

$s21Tests = @(
    "tests\unit\test_s21_all_branches.py",
    "tests\unit\test_paper_runtime_strategy_trust_status.py"
)

if (Test-Path "tests\unit\test_s21_strategy_session.py") {
    $s21Tests += "tests\unit\test_s21_strategy_session.py"
}

$pytestArgs = @("-m", "pytest") + $s21Tests + @("--basetemp=$s21Temp", "-q")
& ".\.venv\Scripts\python.exe" @pytestArgs *>&1 |
    Tee-Object -FilePath (Join-Path $runRoot "s21_focused_validation.txt")

if ($LASTEXITCODE -ne 0) {
    throw "S21 focused validation failed. Historical certification aborted."
}

# ------------------------------------------------------------
# 3. Build historical evidence index from existing TFIS captures
# ------------------------------------------------------------
Write-Step "Indexing existing historical S21 evidence"

$sourceRoot = Join-Path $RepoRoot "data\strategies\S21\fyers_morning_supervised_decision"
$index = @()

foreach ($sessionDate in $SessionDates) {
    $dateRoot = Join-Path $sourceRoot $sessionDate
    $row = [ordered]@{
        session_date = $sessionDate
        source_directory_exists = Test-Path $dateRoot
        snapshot_0916 = $null
        snapshot_0925 = $null
        snapshot_0930 = $null
        option_chain_0916 = $null
        daily_history_0916 = $null
        old_strategy_session = $null
        evidence_status = "MISSING"
    }

    if (Test-Path $dateRoot) {
        $dirs = Get-ChildItem $dateRoot -Directory -ErrorAction SilentlyContinue

        $d0916 = $dirs | Where-Object { $_.Name -match "0916" } | Select-Object -First 1
        $d0925 = $dirs | Where-Object { $_.Name -match "0925" } | Select-Object -First 1
        $d0930 = $dirs | Where-Object { $_.Name -match "0930" } | Select-Object -First 1
        $oldSession = $dirs | Where-Object {
            $_.Name -notmatch "0916|0925|0930"
        } | Select-Object -First 1

        if ($d0916) {
            $row.snapshot_0916 = $d0916.FullName
            $oc = Join-Path $d0916.FullName "normalized_option_chain_snapshot.json"
            $dh = Join-Path $d0916.FullName "normalized_underlying_daily_bars.json"
            if (Test-Path $oc) { $row.option_chain_0916 = $oc }
            if (Test-Path $dh) { $row.daily_history_0916 = $dh }
        }
        if ($d0925) { $row.snapshot_0925 = $d0925.FullName }
        if ($d0930) { $row.snapshot_0930 = $d0930.FullName }
        if ($oldSession) { $row.old_strategy_session = $oldSession.FullName }

        if ($row.option_chain_0916 -and $row.daily_history_0916) {
            $row.evidence_status = "ARCHIVED_0916_MARKET_EVIDENCE_READY"
        } elseif ($row.source_directory_exists) {
            $row.evidence_status = "PARTIAL_ARCHIVED_EVIDENCE"
        }
    }

    $index += [pscustomobject]$row
}

$index | ConvertTo-Json -Depth 6 |
    Set-Content (Join-Path $runRoot "historical_evidence_index.json") -Encoding utf8

$index | Format-Table -AutoSize |
    Out-String |
    Set-Content (Join-Path $runRoot "historical_evidence_index.txt") -Encoding utf8

# ------------------------------------------------------------
# 4. Run one audit collection per date.
#
# This intentionally does NOT pretend the live runner is historical.
# It packages immutable historical evidence and the corrected source/config
# so that each day can be reconstructed without look-ahead.
# ------------------------------------------------------------
Write-Step "Collecting day-by-day S21 certification bundles"

$collectorScript = Join-Path $RepoRoot "COLLECT_S21_REAL_DAY_AUDIT.ps1"
if (-not (Test-Path $collectorScript)) {
    Write-Warning "COLLECT_S21_REAL_DAY_AUDIT.ps1 not found. Day bundles will be built directly."
}

$dayResults = @()

foreach ($sessionDate in $SessionDates) {
    Write-Host "`n--- $sessionDate ---" -ForegroundColor Yellow
    $dayOut = Join-Path $runRoot $sessionDate
    New-Item -ItemType Directory -Force -Path $dayOut | Out-Null

    $sourceDateRoot = Join-Path $sourceRoot $sessionDate

    if (-not (Test-Path $sourceDateRoot)) {
        @{
            session_date = $sessionDate
            verdict = "SKIPPED_NO_ARCHIVED_S21_EVIDENCE"
            note = "No existing S21 market-session artifact directory was found for this date."
        } | ConvertTo-Json -Depth 5 |
            Set-Content (Join-Path $dayOut "day_verdict.json") -Encoding utf8

        $dayResults += [pscustomobject]@{
            session_date = $sessionDate
            verdict = "SKIPPED_NO_ARCHIVED_S21_EVIDENCE"
        }
        continue
    }

    # Copy immutable day evidence.
    Copy-Item $sourceDateRoot (Join-Path $dayOut "archived_runtime_evidence") -Recurse -Force

    # Copy current corrected S21 authority/source for reproducibility.
    $authorityRoot = Join-Path $dayOut "current_s21_authority"
    New-Item -ItemType Directory -Force -Path $authorityRoot | Out-Null

    $authorityPaths = @(
        "config\paper.s21.fyers_connect_test.yaml",
        "config\reference_packets\s21_banknifty_monthly_live_decision_reference.json",
        "config\strategies\options_sell\banknifty",
        "src\tfis\rules\s21_rule_matrix.py",
        "src\tfis\paper\s21_live_decision.py",
        "src\tfis\paper\s21_strategy_session.py",
        "scripts\run_s21_banknifty_0916_supervised_decision.py"
    )

    foreach ($relative in $authorityPaths) {
        $src = Join-Path $RepoRoot $relative
        if (-not (Test-Path $src)) { continue }

        $dst = Join-Path $authorityRoot $relative
        $item = Get-Item $src
        if ($item.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $dst | Out-Null
            Copy-Item (Join-Path $src "*") $dst -Recurse -Force
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent) | Out-Null
            Copy-Item $src $dst -Force
        }
    }

    # Build a compact checkpoint/explainability report from the archived day.
    $py = @'
import json, sys
from pathlib import Path

date_root = Path(sys.argv[1])
out = Path(sys.argv[2])
session_date = sys.argv[3]

def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None

result = {
    "session_date": session_date,
    "evidence_classification": "HISTORICAL_ARCHIVED_MARKET_EVIDENCE",
    "look_ahead_policy": "Only checkpoint artifacts belonging to the requested stage are summarized.",
    "monthly_status_0916": None,
    "eligible_family": None,
    "old_branch_results": [],
    "checkpoint_snapshots": {},
    "gaps": [],
}

snapshot_dirs = [p for p in date_root.iterdir() if p.is_dir()]
for label in ("0916", "0925", "0930"):
    match = next((p for p in snapshot_dirs if label in p.name), None)
    if not match:
        result["gaps"].append(f"MISSING_ARCHIVED_{label}_SNAPSHOT")
        continue
    result["checkpoint_snapshots"][label] = {
        "directory": str(match),
        "has_option_chain": (match / "normalized_option_chain_snapshot.json").exists(),
        "has_underlying_bars": (match / "normalized_underlying_bars.json").exists(),
        "has_daily_bars": (match / "normalized_underlying_daily_bars.json").exists(),
    }

old_session_dirs = [
    p for p in snapshot_dirs
    if not any(x in p.name for x in ("0916", "0925", "0930"))
]
for session in old_session_dirs:
    for branch_dir in session.iterdir():
        if not branch_dir.is_dir():
            continue
        ms = load(branch_dir / "monthly_status_stage_0916.json")
        if ms and result["monthly_status_0916"] is None:
            status = ms.get("monthly_status", {}).get("status")
            result["monthly_status_0916"] = status
            if status in ("BULL", "BULL_CF"):
                result["eligible_family"] = "BULL_CALL_AND_BULL_PUT"
            elif status in ("BEAR", "BEAR_CF"):
                result["eligible_family"] = "BEAR_CALL_AND_BEAR_PUT"

        summary = load(branch_dir / "trade_decision_summary.json")
        order = load(branch_dir / "paper_order_state.json")
        result["old_branch_results"].append({
            "branch": branch_dir.name,
            "decision_status": summary.get("status") if summary else None,
            "selected_contract": summary.get("selected_contract_symbol") if summary else None,
            "entry": summary.get("planned_entry_price") if summary else None,
            "target": summary.get("target_price") if summary else None,
            "stoploss": summary.get("stoploss_price") if summary else None,
            "order_state": order.get("state") if order else None,
            "order_entry": order.get("entry_price") if order else None,
        })

(out / "historical_day_summary.json").write_text(
    json.dumps(result, indent=2, sort_keys=True),
    encoding="utf-8",
)

lines = [
    f"# S21 Historical Day Summary - {session_date}",
    "",
    f"- 09:16 Monthly Status: `{result['monthly_status_0916']}`",
    f"- Eligible Family: `{result['eligible_family']}`",
    "",
    "## Archived Branch Results (old implementation)",
]
for row in result["old_branch_results"]:
    lines += [
        f"### {row['branch']}",
        f"- Decision: `{row['decision_status']}`",
        f"- Contract: `{row['selected_contract']}`",
        f"- Entry: `{row['entry']}`",
        f"- Target: `{row['target']}`",
        f"- SL: `{row['stoploss']}`",
        f"- Order state: `{row['order_state']}`",
        "",
    ]
if result["gaps"]:
    lines += ["## Evidence Gaps"] + [f"- `{x}`" for x in result["gaps"]]

(out / "historical_day_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
'@

    $pyPath = Join-Path $dayOut "_build_day_summary.py"
    $py | Set-Content $pyPath -Encoding utf8

    & ".\.venv\Scripts\python.exe" $pyPath $sourceDateRoot $dayOut $sessionDate
    if ($LASTEXITCODE -ne 0) {
        throw "Historical summary generation failed for $sessionDate"
    }
    Remove-Item $pyPath -Force

    $evidenceRow = $index | Where-Object { $_.session_date -eq $sessionDate }
    $verdict = if (
        $evidenceRow -and
        $evidenceRow.evidence_status -eq "ARCHIVED_0916_MARKET_EVIDENCE_READY"
    ) {
        "READY_FOR_OFFLINE_S21_RECONSTRUCTION"
    } else {
        "PARTIAL_EVIDENCE_REVIEW_ONLY"
    }

    @{
        session_date = $sessionDate
        verdict = $verdict
        note = "No broker order was submitted. This harness packages historical facts for deterministic corrected-S21 reconstruction."
    } | ConvertTo-Json -Depth 5 |
        Set-Content (Join-Path $dayOut "day_verdict.json") -Encoding utf8

    $dayResults += [pscustomobject]@{
        session_date = $sessionDate
        verdict = $verdict
    }
}

# ------------------------------------------------------------
# 5. Multi-day summary
# ------------------------------------------------------------
Write-Step "Writing multi-day certification summary"

$summary = [ordered]@{
    created_at = (Get-Date).ToString("o")
    mode = "WEEKEND_HISTORICAL_READ_ONLY"
    broker_order_authority = "NONE"
    dates_requested = $SessionDates
    s23_non_regression_guard = if ($s23GuardExit -eq 0) { "PASSED" } else { "FAILED" }
    day_results = @($dayResults)
    important_note = @(
        "This harness does not run the live clock backwards.",
        "Archived 09:16/09:25/09:30 market evidence is preserved separately to avoid look-ahead.",
        "Dates without archived historical option-chain/OI evidence are not falsely certified.",
        "The next analysis step is corrected candidate-by-candidate S21 replay on READY_FOR_OFFLINE_S21_RECONSTRUCTION dates."
    )
}

$summary | ConvertTo-Json -Depth 8 |
    Set-Content (Join-Path $runRoot "certification_summary.json") -Encoding utf8

$dayResults | Format-Table -AutoSize |
    Out-String |
    Set-Content (Join-Path $runRoot "certification_summary.txt") -Encoding utf8

# ------------------------------------------------------------
# 6. ZIP
# ------------------------------------------------------------
Write-Step "Creating review ZIP"

$zipPath = Join-Path $RepoRoot "s21_weekend_historical_certification_$timestamp.zip"
if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}
Compress-Archive `
    -Path (Join-Path $runRoot "*") `
    -DestinationPath $zipPath `
    -CompressionLevel Optimal

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host " S21 historical certification evidence created" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "Run directory: $runRoot"
Write-Host "ZIP:           $zipPath" -ForegroundColor Yellow
Write-Host ""
Write-Host "Upload the ZIP here for candidate-by-candidate reconstruction review."
