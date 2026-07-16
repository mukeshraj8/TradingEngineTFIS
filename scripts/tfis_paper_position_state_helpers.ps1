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
