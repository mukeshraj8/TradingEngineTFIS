param(
    [string]$RepoRoot = "D:\TradingEngineTFISRefactored",
    [string]$OutputZip = "",
    [switch]$RunTests
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Add-PathToStage {
    param(
        [Parameter(Mandatory=$true)][string]$RelativePath,
        [Parameter(Mandatory=$true)][string]$StageRoot
    )

    $source = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path $source)) {
        Write-Warning "Not found: $RelativePath"
        return
    }

    $destination = Join-Path $StageRoot $RelativePath
    $item = Get-Item $source

    if ($item.PSIsContainer) {
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Get-ChildItem -Path $source -Recurse -File |
            Where-Object {
                $_.FullName -notmatch '\\(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules|\.venv)\\' -and
                $_.Extension -notin @(".pyc", ".pyo")
            } |
            ForEach-Object {
                $relativeChild = $_.FullName.Substring($source.Length).TrimStart('\')
                $targetFile = Join-Path $destination $relativeChild
                New-Item -ItemType Directory -Force -Path (Split-Path $targetFile -Parent) | Out-Null
                Copy-Item $_.FullName $targetFile -Force
            }
    }
    else {
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item $source $destination -Force
    }
}

if (-not (Test-Path $RepoRoot)) {
    throw "Repository not found: $RepoRoot"
}

$RepoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $RepoRoot

if ([string]::IsNullOrWhiteSpace($OutputZip)) {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $OutputZip = Join-Path $RepoRoot "tfis_remaining_failures_review_$timestamp.zip"
}
elseif (-not [System.IO.Path]::IsPathRooted($OutputZip)) {
    $OutputZip = Join-Path $RepoRoot $OutputZip
}

$stageRoot = Join-Path $env:TEMP ("tfis_review_bundle_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

try {
    Write-Step "Collecting explicit failure-related files"

    $explicitPaths = @(
        "pyproject.toml",
        "AGENTS.md",

        "tests\integration\test_monthly_status_branch_selection_flow.py",
        "tests\integration\test_expiry_day_lifecycle_review.py",
        "tests\integration\test_s23_current_day_fsl_trp_applied_case_comparison.py",
        "tests\integration\test_run_s23_fyers_paper_ingress_cli.py",

        "tests\unit\test_multi_strategy_continuous_supervisor.py",
        "tests\architecture\test_multi_strategy_dashboard_boundaries.py",

        "scripts\run_backtest.py",
        "scripts\run_s23_fyers_paper_ingress.py",

        "src\tfis\monthly_status",
        "src\tfis\backtest",
        "src\tfis\paper",
        "src\tfis\market_structure",
        "src\tfis\contract_selection",
        "src\tfis\strategy",
        "src\tfis\adapters",
        "src\tfis\runtime\multi_strategy",
        "src\tfis\persistence",
        "src\tfis\internal_paper",

        "config\strategies\options_sell\nifty",
        "config\monthly_status_instruments.yaml",

        "tests\fixtures\backtest",

        "docs\operations\current_state.md",
        "docs\operations\next_steps.md",
        "docs\operations\milestones.md"
    )

    foreach ($path in $explicitPaths) {
        Add-PathToStage -RelativePath $path -StageRoot $stageRoot
    }

    Write-Step "Finding implementation files by failure-related search terms"

    $patterns = @(
        "expiry_day_review",
        "expiry_day_candidates",
        "expiry_day_exit_satisfied",
        "expiry_day_exit_pending",
        "requires full exit",
        "BULL_CF",
        "BEAR_CF",
        "monthly_status",
        "current_day",
        "FSL",
        "TRP",
        "start_strike",
        "selected_strike",
        "CDHH",
        "CDLL",
        "PRV_2DHH",
        "PRV_3DLL",
        "Preflight only never connects"
    )

    $searchRoots = @("src", "scripts", "tests", "config")
    $matchedFiles = New-Object System.Collections.Generic.HashSet[string]

    foreach ($root in $searchRoots) {
        $absoluteRoot = Join-Path $RepoRoot $root
        if (-not (Test-Path $absoluteRoot)) { continue }

        Get-ChildItem -Path $absoluteRoot -Recurse -File |
            Where-Object {
                $_.FullName -notmatch '\\(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|node_modules|\.venv)\\' -and
                $_.Extension -in @(".py", ".yaml", ".yml", ".json", ".toml", ".md", ".csv")
            } |
            ForEach-Object {
                $file = $_
                try {
                    $content = Get-Content -Path $file.FullName -Raw -ErrorAction Stop
                    foreach ($pattern in $patterns) {
                        if ($content -match [regex]::Escape($pattern)) {
                            $relative = $file.FullName.Substring($RepoRoot.Length).TrimStart('\')
                            [void]$matchedFiles.Add($relative)
                            break
                        }
                    }
                }
                catch {
                    Write-Warning "Could not inspect: $($file.FullName)"
                }
            }
    }

    foreach ($relative in ($matchedFiles | Sort-Object)) {
        Add-PathToStage -RelativePath $relative -StageRoot $stageRoot
    }

    Write-Step "Collecting directly imported local modules from the four failing integration tests"

    $testFiles = @(
        "tests\integration\test_monthly_status_branch_selection_flow.py",
        "tests\integration\test_expiry_day_lifecycle_review.py",
        "tests\integration\test_s23_current_day_fsl_trp_applied_case_comparison.py",
        "tests\integration\test_run_s23_fyers_paper_ingress_cli.py"
    )

    foreach ($testRelative in $testFiles) {
        $testPath = Join-Path $RepoRoot $testRelative
        if (-not (Test-Path $testPath)) { continue }

        $lines = Get-Content $testPath
        foreach ($line in $lines) {
            if ($line -match '^\s*from\s+([A-Za-z0-9_\.]+)\s+import\s+' -or
                $line -match '^\s*import\s+([A-Za-z0-9_\.]+)') {

                $module = $Matches[1]
                if ($module.StartsWith("tfis.")) {
                    $relativeModule = "src\" + ($module.Replace(".", "\")) + ".py"
                    if (Test-Path (Join-Path $RepoRoot $relativeModule)) {
                        Add-PathToStage -RelativePath $relativeModule -StageRoot $stageRoot
                    }
                    else {
                        $relativePackage = "src\" + ($module.Replace(".", "\"))
                        if (Test-Path (Join-Path $RepoRoot $relativePackage)) {
                            Add-PathToStage -RelativePath $relativePackage -StageRoot $stageRoot
                        }
                    }
                }
                elseif ($module.StartsWith("scripts.")) {
                    $relativeScript = ($module.Replace(".", "\")) + ".py"
                    if (Test-Path (Join-Path $RepoRoot $relativeScript)) {
                        Add-PathToStage -RelativePath $relativeScript -StageRoot $stageRoot
                    }
                }
            }
        }
    }

    if ($RunTests) {
        Write-Step "Running the full suite and capturing remaining failures"
        $failureLog = Join-Path $stageRoot "remaining_failures.txt"
        $baseTemp = Join-Path $RepoRoot ".pytest_tmp\review_bundle"

        Remove-Item -Recurse -Force $baseTemp -ErrorAction SilentlyContinue

        & ".\.venv\Scripts\python.exe" -m pytest `
            "--basetemp=$baseTemp" `
            -q *>&1 | Tee-Object -FilePath $failureLog

        $pytestExitCode = $LASTEXITCODE
        "Pytest exit code: $pytestExitCode" |
            Out-File -FilePath (Join-Path $stageRoot "pytest_exit_code.txt") -Encoding utf8
    }
    else {
        $existingLogs = @(
            "remaining_failures.txt",
            "pytest_output.txt",
            "full_pytest_output.txt"
        )
        foreach ($log in $existingLogs) {
            if (Test-Path (Join-Path $RepoRoot $log)) {
                Add-PathToStage -RelativePath $log -StageRoot $stageRoot
            }
        }
    }

    Write-Step "Writing bundle manifest"

    $manifestFiles = Get-ChildItem -Path $stageRoot -Recurse -File |
        ForEach-Object {
            $_.FullName.Substring($stageRoot.Length).TrimStart('\')
        } |
        Sort-Object

    $manifest = [ordered]@{
        created_at = (Get-Date).ToString("o")
        repository_root = $RepoRoot
        output_zip = $OutputZip
        run_tests = [bool]$RunTests
        matched_search_file_count = $matchedFiles.Count
        total_file_count = $manifestFiles.Count
        search_patterns = $patterns
        files = $manifestFiles
    }

    $manifest |
        ConvertTo-Json -Depth 8 |
        Set-Content -Path (Join-Path $stageRoot "bundle_manifest.json") -Encoding utf8

    @"
TFIS Remaining Failures Review Bundle

Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Repository: $RepoRoot

Contents:
- Monthly Status implementation and tests
- Expiry-day lifecycle implementation, tests, and fixtures
- S23 current-day FSL/TRP implementation, tests, configs, and fixtures
- FYERS paper-ingress CLI implementation and tests
- Runtime, persistence, internal-paper, and supporting modules
- Search-matched implementation files
- Optional full pytest output when -RunTests is supplied
- bundle_manifest.json

This bundle intentionally excludes:
- .venv
- __pycache__
- pytest caches
- node_modules
- compiled Python files
- live credentials/tokens
- large runtime data directories
"@ | Set-Content -Path (Join-Path $stageRoot "README_BUNDLE.txt") -Encoding utf8

    Write-Step "Creating ZIP"

    if (Test-Path $OutputZip) {
        Remove-Item -Force $OutputZip
    }

    Compress-Archive -Path (Join-Path $stageRoot "*") -DestinationPath $OutputZip -CompressionLevel Optimal

    $zipInfo = Get-Item $OutputZip
    Write-Host "`nBundle created successfully:" -ForegroundColor Green
    Write-Host $zipInfo.FullName -ForegroundColor Yellow
    Write-Host ("Size: {0:N2} MB" -f ($zipInfo.Length / 1MB))
    Write-Host ("Files: {0}" -f $manifestFiles.Count)
}
finally {
    if (Test-Path $stageRoot) {
        Remove-Item -Recurse -Force $stageRoot -ErrorAction SilentlyContinue
    }
}
