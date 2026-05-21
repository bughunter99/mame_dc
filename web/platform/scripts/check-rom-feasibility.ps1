param(
    [string]$RomZipPath = "web/platform/roms/sf2ce.zip",
    [string]$Machine = "sf2ce",
    [string]$RuntimeLogPath = "",
    [switch]$AutoSelectMachine,
    [string]$JsonOutputPath = ""
)

$ErrorActionPreference = "Stop"

function Get-RepositoryRoot {
    param([string]$StartPath)

    $current = Resolve-Path $StartPath
    while ($true) {
        if ((Test-Path (Join-Path $current "makefile") -PathType Leaf) -and (Test-Path (Join-Path $current "src") -PathType Container)) {
            return $current.Path
        }
        $parent = Split-Path $current -Parent
        if (-not $parent -or $parent -eq $current.Path) {
            throw "Repository root not found from $StartPath"
        }
        $current = Resolve-Path $parent
    }
}

function Read-ZipEntries {
    param([string]$Path)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        return $zip.Entries | ForEach-Object { $_.FullName.ToLowerInvariant() }
    }
    finally {
        $zip.Dispose()
    }
}

function Get-MissingFromMarkers {
    param(
        [string[]]$Entries,
        [string[]]$Markers
    )

    $set = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($e in $Entries) {
        [void]$set.Add($e)
    }

    $missing = @()
    foreach ($marker in $Markers) {
        if (-not $set.Contains($marker)) {
            $missing += $marker
        }
    }
    return $missing
}

function Parse-MissingFromRuntimeLog {
    param([string]$Path)

    if (-not (Test-Path $Path -PathType Leaf)) {
        return @()
    }

    $content = Get-Content -Path $Path -Raw
    $regex = '(?im)\b([a-z0-9_\-]+\.(?:bin|rom|ic\d+|\d+[a-z]?))\b.{0,40}\b(not found|missing|bad|incorrect)\b|\b(not found|missing|bad|incorrect)\b.{0,40}\b([a-z0-9_\-]+\.(?:bin|rom|ic\d+|\d+[a-z]?))\b'
    $matches = [regex]::Matches($content, $regex)
    $results = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)

    foreach ($m in $matches) {
        foreach ($g in $m.Groups) {
            $v = "$($g.Value)".Trim().ToLowerInvariant()
            if ($v -match '\.(bin|rom|ic\d+|\d+[a-z]?)$') {
                [void]$results.Add($v)
            }
        }
    }

    return $results.ToArray() | Sort-Object
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Get-RepositoryRoot -StartPath $scriptRoot
$resolvedRomPath = Join-Path $repoRoot $RomZipPath

if (-not (Test-Path $resolvedRomPath -PathType Leaf)) {
    throw "ROM zip not found: $resolvedRomPath"
}

$entries = Read-ZipEntries -Path $resolvedRomPath
$entryCount = $entries.Count

$sf2ceMarkers = @(
    "s92e_23b.8f",
    "s92_21a.bin",
    "s92_09.12a",
    "s92-1m.3a",
    "s92-13m.6c"
)

$sf2rbMarkers = @(
    "sf2ce.23",
    "sf2ce.22",
    "s92_21a.bin",
    "s92_09.12a",
    "s92-13m.6c"
)

$machineLower = $Machine.ToLowerInvariant()
$sf2ceMissing = Get-MissingFromMarkers -Entries $entries -Markers $sf2ceMarkers
$sf2rbMissing = Get-MissingFromMarkers -Entries $entries -Markers $sf2rbMarkers
$likelyMachine = if ($sf2ceMissing.Count -lt $sf2rbMissing.Count) { "sf2ce" } elseif ($sf2rbMissing.Count -lt $sf2ceMissing.Count) { "sf2rb" } else { "undetermined" }

if ($AutoSelectMachine -and $likelyMachine -ne "undetermined") {
    $machineLower = $likelyMachine
    $Machine = $likelyMachine
}

$selectedMarkers = if ($machineLower -eq "sf2rb") { $sf2rbMarkers } else { $sf2ceMarkers }
$missing = Get-MissingFromMarkers -Entries $entries -Markers $selectedMarkers

$runtimeMissing = @()
if ($RuntimeLogPath) {
    $resolvedLogPath = if ([System.IO.Path]::IsPathRooted($RuntimeLogPath)) { $RuntimeLogPath } else { Join-Path $repoRoot $RuntimeLogPath }
    $runtimeMissing = Parse-MissingFromRuntimeLog -Path $resolvedLogPath
}

Write-Host "=== ROM Feasibility Report ==="
Write-Host "ROM zip         : $resolvedRomPath"
Write-Host "Machine target  : $Machine"
Write-Host "Entries in zip  : $entryCount"
Write-Host "Likely machine  : $likelyMachine"
Write-Host ""
Write-Host "Marker check for target machine:"

if ($missing.Count -eq 0) {
    Write-Host "- OK: marker files found"
}
else {
    Write-Host "- Missing marker files:"
    $missing | ForEach-Object { Write-Host "  - $_" }
}

if ($runtimeMissing.Count -gt 0) {
    Write-Host ""
    Write-Host "Runtime log hints (missing/bad files):"
    $runtimeMissing | ForEach-Object { Write-Host "  - $_" }
}

Write-Host ""
$resultMessage = ""
if ($missing.Count -eq 0 -and $runtimeMissing.Count -eq 0) {
    $resultMessage = "Candidate ROM looks feasible for browser/mobile test."
}
elseif ($missing.Count -gt 0 -and $runtimeMissing.Count -eq 0) {
    $resultMessage = "ROM set likely mismatched for '$Machine'. Verify CRC-exact set before web/mobile validation."
}
else {
    $resultMessage = "ROM mismatch indicators found. Use runtime hints to replace missing/bad files in the set."
}

Write-Host "Result: $resultMessage"

if ($JsonOutputPath) {
    $resolvedJsonPath = if ([System.IO.Path]::IsPathRooted($JsonOutputPath)) { $JsonOutputPath } else { Join-Path $repoRoot $JsonOutputPath }
    $report = [ordered]@{
        romZip = $resolvedRomPath
        selectedMachine = $Machine
        likelyMachine = $likelyMachine
        entryCount = $entryCount
        missingMarkers = $missing
        sf2ceMissingCount = $sf2ceMissing.Count
        sf2rbMissingCount = $sf2rbMissing.Count
        runtimeMissingHints = $runtimeMissing
        result = $resultMessage
        generatedAt = (Get-Date).ToString("s")
    }
    $json = $report | ConvertTo-Json -Depth 6
    Set-Content -Path $resolvedJsonPath -Value $json -Encoding UTF8
    Write-Host "JSON report     : $resolvedJsonPath"
}
