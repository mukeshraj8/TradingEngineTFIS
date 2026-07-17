function Resolve-TfisPythonExecutable {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [switch]$AllowSystemPythonFallback
    )

    $pythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $pythonExe) {
        return $pythonExe
    }
    if ($AllowSystemPythonFallback) {
        return "python"
    }
    throw "Missing python executable: $pythonExe"
}

function New-TfisTaskLaunchContext {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$RelativeLogDirectory,
        [Parameter(Mandatory = $true)]
        [string]$LogFilePrefix
    )

    $logDirectory = Join-Path $RepoRoot $RelativeLogDirectory
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $stamp = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmssfff"), $PID
    $logPath = Join-Path $logDirectory "${LogFilePrefix}_$stamp.log"

    return [pscustomobject]@{
        LogDirectory = $logDirectory
        Stamp = $stamp
        LogPath = $logPath
    }
}

function Write-TfisTaskLogMessage {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LogPath,
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [string]$ConsolePrefix = "",
        [string]$TimestampFormat = "yyyy-MM-ddTHH:mm:ssK"
    )

    $line = "{0} {1}" -f (Get-Date -Format $TimestampFormat), $Message
    Add-Content -Path $LogPath -Value $line

    if ([string]::IsNullOrWhiteSpace($ConsolePrefix)) {
        Write-Host $Message
        return
    }

    Write-Host "$ConsolePrefix$Message"
}

function Get-TfisLatestSessionMetadataFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArtifactRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$SessionDate
    )

    $dayRoot = Join-Path $ArtifactRoot $SessionDate.ToString("yyyy-MM-dd")
    if (-not (Test-Path $dayRoot)) {
        return $null
    }

    return Get-ChildItem -Path $dayRoot -Recurse -Filter "scheduled_run_metadata.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Show-TfisTaskBanner {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$LogPath
    )

    Write-Host "============================================================"
    Write-Host $Title
    Write-Host "This window belongs to TradingEngineTFIS only."
    Write-Host "Repo: $RepoRoot"
    Write-Host "Log : $LogPath"
    Write-Host "============================================================"
}

function Start-TfisHiddenPythonProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExecutable,
        [Parameter(Mandatory = $true)]
        [object[]]$ArgumentList,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory,
        [Parameter(Mandatory = $true)]
        [string]$StdoutPath,
        [Parameter(Mandatory = $true)]
        [string]$StderrPath
    )

    return Start-Process `
        -FilePath $PythonExecutable `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -Wait `
        -PassThru `
        -WindowStyle Hidden
}
