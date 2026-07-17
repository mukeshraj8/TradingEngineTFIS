function Resolve-TfisRepoRelativePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [string]$PathText
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return $null
    }
    if ([System.IO.Path]::IsPathRooted($PathText)) {
        return [System.IO.Path]::GetFullPath($PathText)
    }
    return [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $PathText))
}

function Get-TfisEffectiveRunDate {
    param([datetime]$RunDate)

    if ($RunDate) {
        return $RunDate.Date
    }
    return (Get-Date).Date
}

function Get-TfisTradingHolidayEntry {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$EffectiveDate,
        [string]$CalendarPath
    )

    $resolvedCalendar = Resolve-TfisRepoRelativePath -RepoRoot $RepoRoot -PathText $CalendarPath
    if (-not $resolvedCalendar -or -not (Test-Path $resolvedCalendar)) {
        return $null
    }

    try {
        $holidayJson = Get-Content -Path $resolvedCalendar -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }

    foreach ($entry in @($holidayJson.holidays)) {
        $dateText = [string]$entry.date
        if ($dateText -and $dateText -eq $EffectiveDate.ToString("yyyy-MM-dd")) {
            return $entry
        }
    }
    return $null
}

function Test-TfisTradingHolidayDate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$EffectiveDate,
        [string]$CalendarPath
    )

    return $null -ne (Get-TfisTradingHolidayEntry -RepoRoot $RepoRoot -EffectiveDate $EffectiveDate -CalendarPath $CalendarPath)
}

function Get-TfisNoRunReason {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [datetime]$EffectiveDate,
        [string]$CalendarPath
    )

    if ($EffectiveDate.DayOfWeek -eq [System.DayOfWeek]::Saturday -or $EffectiveDate.DayOfWeek -eq [System.DayOfWeek]::Sunday) {
        return "WEEKEND_NO_ACTION: $($EffectiveDate.ToString('yyyy-MM-dd')) is $($EffectiveDate.DayOfWeek); NSE equity/F&O market is closed."
    }

    $holiday = Get-TfisTradingHolidayEntry -RepoRoot $RepoRoot -EffectiveDate $EffectiveDate -CalendarPath $CalendarPath
    if ($holiday) {
        return "NSE_HOLIDAY_NO_ACTION: $($EffectiveDate.ToString('yyyy-MM-dd')) is configured as NSE holiday '$($holiday.name)'."
    }

    return $null
}
