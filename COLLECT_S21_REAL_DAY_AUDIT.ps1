param(
    [string]$RepoRoot = "D:\TradingEngineTFIS",
    [string]$SessionDate = "2026-08-06"
)

$ErrorActionPreference = "Stop"

Set-Location $RepoRoot

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host " TFIS S21 REAL-DAY AUDIT" -ForegroundColor Cyan
Write-Host " Session: $SessionDate" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$auditRoot = Join-Path $RepoRoot "reports\s21_real_day_audit\$SessionDate"
$bundleRoot = Join-Path $env:TEMP "tfis_s21_audit_$timestamp"
$zipPath = Join-Path $RepoRoot "s21_real_day_audit_${SessionDate}_$timestamp.zip"

Remove-Item -Recurse -Force $bundleRoot -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $bundleRoot | Out-Null
New-Item -ItemType Directory -Force $auditRoot | Out-Null


# --------------------------------------------------
# 1. Record repository state
# --------------------------------------------------

Write-Host ""
Write-Host "1. Recording repository state..." -ForegroundColor Yellow

git status --short |
    Out-File "$bundleRoot\git_status.txt" -Encoding utf8

git rev-parse HEAD |
    Out-File "$bundleRoot\git_head.txt" -Encoding utf8

git diff |
    Out-File "$bundleRoot\git_diff.patch" -Encoding utf8


# --------------------------------------------------
# 2. Run S21 focused tests
# --------------------------------------------------

Write-Host ""
Write-Host "2. Running S21 focused validation..." -ForegroundColor Yellow

$pytestTemp = ".pytest_tmp\s21_real_day_audit"

Remove-Item -Recurse -Force $pytestTemp -ErrorAction SilentlyContinue

& ".\.venv\Scripts\python.exe" -m pytest `
    tests\unit\test_s21_all_branches.py `
    tests\unit\test_paper_runtime_strategy_trust_status.py `
    "--basetemp=$pytestTemp" `
    -q *>&1 |
    Tee-Object -FilePath "$bundleRoot\s21_focused_tests.txt"

"S21 focused pytest exit code: $LASTEXITCODE" |
    Out-File "$bundleRoot\s21_focused_tests_exit_code.txt"


# --------------------------------------------------
# 3. Find S21 runnable scripts
# --------------------------------------------------

Write-Host ""
Write-Host "3. Finding S21 runtime commands..." -ForegroundColor Yellow

Get-ChildItem -Recurse -File scripts,src |
    Select-String -Pattern `
        "run_s21|S21.*morning|S21.*supervised|paper.s21|BANKNIFTY.*supervised" |
    Select-Object Path,LineNumber,Line |
    Format-Table -AutoSize |
    Out-String |
    Out-File "$bundleRoot\s21_runtime_search.txt" -Encoding utf8


# --------------------------------------------------
# 4. Attempt historical/current S21 runtime
# --------------------------------------------------

Write-Host ""
Write-Host "4. Looking for runnable S21 entry point..." -ForegroundColor Yellow

$candidateScripts = @(
    "scripts\run_s21_fyers_morning_supervised_decision.py",
    "scripts\run_s21_fyers_supervised_decision.py",
    "scripts\run_s21_paper.py",
    "scripts\run_paper_morning_supervised.py"
)

$runnerFound = $false

foreach ($script in $candidateScripts) {

    if (Test-Path $script) {

        Write-Host "Found candidate runner: $script" -ForegroundColor Green

        try {
            & ".\.venv\Scripts\python.exe" $script `
                --help *>&1 |
                Out-File "$bundleRoot\runner_help.txt" -Encoding utf8
        }
        catch {
            $_ | Out-File "$bundleRoot\runner_help_error.txt"
        }

        $runnerFound = $true
        break
    }
}

if (-not $runnerFound) {

    Write-Warning "No obvious standalone S21 runner found."

    Get-ChildItem -Recurse -File scripts |
        Select-String -Pattern "S21|paper.s21|BANKNIFTY" |
        Select-Object Path,LineNumber,Line |
        Format-Table -AutoSize |
        Out-String |
        Out-File "$bundleRoot\candidate_runner_search.txt" -Encoding utf8
}


# --------------------------------------------------
# 5. Gather all S21 reports/data for the chosen date
# --------------------------------------------------

Write-Host ""
Write-Host "5. Collecting S21 artifacts for $SessionDate..." -ForegroundColor Yellow

$searchRoots = @(
    "data",
    "reports",
    "logs",
    "tmp"
)

foreach ($root in $searchRoots) {

    if (-not (Test-Path $root)) {
        continue
    }

    Get-ChildItem -Path $root -Recurse -File |
        Where-Object {
            $_.FullName -match "S21|s21|BANKNIFTY|banknifty" -and
            (
                $_.FullName -match $SessionDate -or
                $_.Name -match ($SessionDate -replace "-", "")
            )
        } |
        ForEach-Object {

            $relative = $_.FullName.Substring($RepoRoot.Length).TrimStart('\')
            $dest = Join-Path $bundleRoot $relative

            New-Item -ItemType Directory -Force `
                -Path (Split-Path $dest -Parent) |
                Out-Null

            Copy-Item $_.FullName $dest -Force
        }
}


# --------------------------------------------------
# 6. Gather recent S21 artifacts even if filenames
#    do not include session date
# --------------------------------------------------

Write-Host ""
Write-Host "6. Collecting recent S21 state/evidence..." -ForegroundColor Yellow

$importantNames = @(
    "paper_order_state.json",
    "paper_order_events.jsonl",
    "final_decision_summary.json",
    "decision_explainer.json",
    "decision_timeline.json",
    "option_chain_snapshot.json",
    "normalized_option_chain.json",
    "selected_contract",
    "monthly_status",
    "reference_packet",
    "prelude",
    "runtime_input"
)

Get-ChildItem -Path data,reports -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {

        $full = $_.FullName.ToLower()

        if ($full -notmatch "s21|banknifty") {
            return $false
        }

        foreach ($name in $importantNames) {
            if ($_.Name.ToLower().Contains($name.ToLower())) {
                return $true
            }
        }

        return $false
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 200 |
    ForEach-Object {

        $relative = $_.FullName.Substring($RepoRoot.Length).TrimStart('\')
        $dest = Join-Path $bundleRoot "recent\$relative"

        New-Item -ItemType Directory -Force `
            -Path (Split-Path $dest -Parent) |
            Out-Null

        Copy-Item $_.FullName $dest -Force
    }


# --------------------------------------------------
# 7. Collect S21 configs and source used by runtime
# --------------------------------------------------

Write-Host ""
Write-Host "7. Collecting S21 configuration/source..." -ForegroundColor Yellow

$paths = @(
    "config\paper.s21.fyers_connect_test.yaml",
    "config\strategies\options_sell\banknifty",
    "src\tfis\rules\s21_rule_matrix.py",
    "src\tfis\paper\s21_live_decision.py",
    "src\tfis\paper\live_decision_timeline_runner.py",
    "src\tfis\paper\runtime_input_derivation.py",
    "src\tfis\paper\runtime_strategy_trust_status.py"
)

foreach ($path in $paths) {

    if (-not (Test-Path $path)) {
        continue
    }

    $item = Get-Item $path

    if ($item.PSIsContainer) {

        Get-ChildItem $path -Recurse -File |
            ForEach-Object {

                $relative = $_.FullName.Substring($RepoRoot.Length).TrimStart('\')
                $dest = Join-Path $bundleRoot $relative

                New-Item -ItemType Directory -Force `
                    -Path (Split-Path $dest -Parent) |
                    Out-Null

                Copy-Item $_.FullName $dest -Force
            }

    }
    else {

        $relative = $item.FullName.Substring($RepoRoot.Length).TrimStart('\')
        $dest = Join-Path $bundleRoot $relative

        New-Item -ItemType Directory -Force `
            -Path (Split-Path $dest -Parent) |
            Out-Null

        Copy-Item $item.FullName $dest -Force
    }
}


# --------------------------------------------------
# 8. Write manifest
# --------------------------------------------------

Write-Host ""
Write-Host "8. Writing manifest..." -ForegroundColor Yellow

$files = Get-ChildItem $bundleRoot -Recurse -File |
    ForEach-Object {
        $_.FullName.Substring($bundleRoot.Length).TrimStart('\')
    } |
    Sort-Object

$manifest = [ordered]@{
    created_at = (Get-Date).ToString("o")
    repo_root = $RepoRoot
    session_date = $SessionDate
    file_count = $files.Count
    files = $files
}

$manifest |
    ConvertTo-Json -Depth 8 |
    Set-Content "$bundleRoot\manifest.json" -Encoding utf8


# --------------------------------------------------
# 9. ZIP everything
# --------------------------------------------------

Write-Host ""
Write-Host "9. Creating ZIP..." -ForegroundColor Yellow

if (Test-Path $zipPath) {
    Remove-Item -Force $zipPath
}

Compress-Archive `
    -Path "$bundleRoot\*" `
    -DestinationPath $zipPath `
    -CompressionLevel Optimal

Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host " Audit bundle created successfully" -ForegroundColor Green
Write-Host " $zipPath" -ForegroundColor Yellow
Write-Host " Files: $($files.Count)" -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Green

Remove-Item -Recurse -Force $bundleRoot -ErrorAction SilentlyContinue