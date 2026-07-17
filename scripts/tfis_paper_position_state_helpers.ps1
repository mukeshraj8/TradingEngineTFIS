function Test-TfisResumablePaperPositionStateJson {
    param(
        [Parameter(Mandatory = $true)]
        $StateJson,

        [datetime]$EffectiveDate
    )

    $status = [string]$StateJson.lifecycle_status
    if ($status -notin @(
        "PAPER_POSITION_OPEN",
        "PAPER_POSITION_CARRIED_FORWARD",
        "PAPER_POSITION_RESUMED"
    )) {
        return $false
    }

    if ($false -eq [bool]$StateJson.carry_forward_allowed) {
        return $false
    }

    if ($EffectiveDate -and $StateJson.expiry_date) {
        try {
            $expiryDate = [datetime]::Parse([string]$StateJson.expiry_date).Date
            if ($expiryDate -lt $EffectiveDate.Date) {
                return $false
            }
        }
        catch {
            return $true
        }
    }

    return $true
}

function Resolve-TfisAbsolutePathText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$PathText
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return ""
    }

    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PathText))
}

function Resolve-TfisPositionStateDirectoryPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$PathText
    )

    $absolutePath = Resolve-TfisAbsolutePathText -RepoRoot $RepoRoot -PathText $PathText
    if ([string]::IsNullOrWhiteSpace($absolutePath)) {
        return ""
    }

    if ((Split-Path -Leaf $absolutePath) -eq "paper_position_state.json" -or (Test-Path -Path $absolutePath -PathType Leaf)) {
        return [System.IO.Path]::GetDirectoryName($absolutePath)
    }

    return $absolutePath
}

function Get-TfisResumablePaperPositionStatePaths {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ArtifactRoot,

        [datetime]$EffectiveDate
    )

    if (-not (Test-Path $ArtifactRoot)) {
        return @()
    }

    return @(
        Get-ChildItem -Path $ArtifactRoot -Recurse -Filter "paper_position_state.json" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        ForEach-Object {
            try {
                $stateJson = Get-Content -Path $_.FullName -Raw | ConvertFrom-Json
            }
            catch {
                return
            }

            if (-not (Test-TfisResumablePaperPositionStateJson -StateJson $stateJson -EffectiveDate $EffectiveDate)) {
                return
            }
            $_.FullName
        } |
        Select-Object -Unique
    )
}
