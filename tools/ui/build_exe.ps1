Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = (Resolve-Path (Join-Path $scriptDir "..\..")).Path

Set-Location $repoRoot

Write-Host "[build] installing pixi environment: repo root"
pixi install

Write-Host "[build] building onefile exe with PyInstaller"
pixi run ui-build

$exePath = Join-Path $repoRoot "tools\ui\dist\GameSetupUI.exe"
if (-not (Test-Path $exePath)) {
    throw "build succeeded but exe not found: $exePath"
}

$distRoot = Join-Path $repoRoot "dist"
if (-not (Test-Path $distRoot)) {
    New-Item -ItemType Directory -Path $distRoot -Force | Out-Null
}

$distExe = Join-Path $distRoot "GameSetupUI.exe"
$copied = $false
$copyError = $null
for ($i = 1; $i -le 6; $i++) {
    try {
        Copy-Item -Path $exePath -Destination $distExe -Force
        $copied = $true
        break
    }
    catch {
        $copyError = $_.Exception.Message
        Start-Sleep -Milliseconds 500
    }
}

Write-Host "[build] exe: $exePath"
if ($copied) {
    Write-Host "[build] copied: $distExe"
}
else {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $fallbackExe = Join-Path $distRoot ("GameSetupUI_" + $stamp + ".exe")
    Copy-Item -Path $exePath -Destination $fallbackExe -Force
    Write-Warning "[build] could not overwrite ${distExe}: $copyError"
    Write-Warning "[build] wrote fallback copy: $fallbackExe"
}
