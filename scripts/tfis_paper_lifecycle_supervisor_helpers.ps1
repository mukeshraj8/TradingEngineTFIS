function Resolve-TfisPaperLifecycleSupervisorLauncherPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $launcherPath = Join-Path $RepoRoot "scripts\start_tfis_paper_lifecycle_supervisor.ps1"
    if (-not (Test-Path $launcherPath)) {
        throw "Missing TFIS lifecycle supervisor launcher: $launcherPath"
    }
    return $launcherPath
}

function Start-TfisPaperLifecycleSupervisorProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$TfisRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$SessionDate,
        [switch]$SkipRefresh,
        [switch]$DisableDashboardRebuild,
        [string]$TargetsConfig,
        [string]$DashboardOutputRoot,
        [Nullable[int]]$DashboardPort
    )

    $launcherPath = Resolve-TfisPaperLifecycleSupervisorLauncherPath -RepoRoot $RepoRoot
    $supervisorArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", $launcherPath,
        "-TfisRoot", $TfisRoot,
        "-SessionDate", $SessionDate.ToString("yyyy-MM-dd")
    )

    if ($TargetsConfig) {
        $supervisorArgs += "-TargetsConfig"
        $supervisorArgs += $TargetsConfig
    }
    if ($DashboardOutputRoot) {
        $supervisorArgs += "-DashboardOutputRoot"
        $supervisorArgs += $DashboardOutputRoot
    }
    if ($DashboardPort.HasValue) {
        $supervisorArgs += "-DashboardPort"
        $supervisorArgs += "$($DashboardPort.Value)"
    }
    if ($DisableDashboardRebuild) {
        $supervisorArgs += "-DisableDashboardRebuild"
    }
    if ($SkipRefresh) {
        $supervisorArgs += "-SkipRefresh"
    }

    return Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList $supervisorArgs `
        -WorkingDirectory $RepoRoot `
        -WindowStyle Normal `
        -PassThru
}
