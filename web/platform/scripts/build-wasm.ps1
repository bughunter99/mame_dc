param(
    [string]$Subtarget = "sf2ce",
    [string]$Sources = "src/mame/capcom/fcrash.cpp",
    [string]$OutputDirectory = "web/platform/frontend/static/wasm",
    [int]$Jobs = [Environment]::ProcessorCount
)

$ErrorActionPreference = "Stop"

function Get-RepositoryRoot {
    param(
        [string]$StartPath
    )

    $current = Resolve-Path $StartPath
    while ($true) {
        $makefilePath = Join-Path $current "makefile"
        $srcPath = Join-Path $current "src"
        if ((Test-Path $makefilePath -PathType Leaf) -and (Test-Path $srcPath -PathType Container)) {
            return $current.Path
        }

        $parent = Split-Path $current -Parent
        if (-not $parent -or $parent -eq $current.Path) {
            throw "Repository root not found starting from $StartPath"
        }
        $current = Resolve-Path $parent
    }
}

function Get-LatestFile {
    param(
        [string]$Path,
        [string]$Filter,
        [datetime]$Since
    )

    Get-ChildItem -Path $Path -Recurse -Filter $Filter -File |
        Where-Object { $_.LastWriteTime -ge $Since } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$repositoryRoot = Get-RepositoryRoot -StartPath $scriptRoot
$outputPath = Join-Path $repositoryRoot $OutputDirectory

if (-not (Get-Command emmake -ErrorAction SilentlyContinue)) {
    throw "emmake was not found on PATH. Install Emscripten first, then run emsdk_env.bat before this script."
}

New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

Write-Host "Repository root: $repositoryRoot"
Write-Host "Building subtarget: $Subtarget"
Write-Host "Sources: $Sources"
Write-Host "Output directory: $outputPath"

$buildStartedAt = Get-Date
$makeArguments = @(
    "make",
    "SUBTARGET=$Subtarget",
    "SOURCES=$Sources",
    "WEBASSEMBLY=1",
    "-j$Jobs"
)

Push-Location $repositoryRoot
try {
    & emmake @makeArguments
    if ($LASTEXITCODE -ne 0) {
        throw "emmake failed with exit code $LASTEXITCODE"
    }

    $jsFile = Get-LatestFile -Path $repositoryRoot -Filter "*.js" -Since $buildStartedAt
    $wasmFile = Get-LatestFile -Path $repositoryRoot -Filter "*.wasm" -Since $buildStartedAt

    if (-not $jsFile) {
        throw "No .js file was produced by the build."
    }
    if (-not $wasmFile) {
        throw "No .wasm file was produced by the build."
    }

    Copy-Item $jsFile.FullName (Join-Path $outputPath "mame.js") -Force
    Copy-Item $wasmFile.FullName (Join-Path $outputPath "mame.wasm") -Force

    $webBuildLog = Join-Path $outputPath "build-info.txt"
    @"
Built at: $((Get-Date).ToString("s"))
Source subtarget: $Subtarget
Source list: $Sources
JS source: $($jsFile.FullName)
WASM source: $($wasmFile.FullName)
"@ | Set-Content -Path $webBuildLog -Encoding UTF8

    Write-Host "Copied to $outputPath\mame.js and $outputPath\mame.wasm"
}
finally {
    Pop-Location
}
