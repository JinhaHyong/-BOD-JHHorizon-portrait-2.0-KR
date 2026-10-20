param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'dist'),
    [ValidateSet('folder', 'single')][string]$Mode = 'folder'
)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    $python = (Get-Command python -ErrorAction Stop).Source
    $oldPath = $env:PATH
    $oldMode = $env:JHNODE_BUILD_MODE
    $env:JHNODE_BUILD_MODE = $Mode
    $env:PATH = (Split-Path -Parent $python) + ';' + (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
    & $python -m PyInstaller --noconfirm --clean --distpath $OutputDirectory --workpath (Join-Path $PSScriptRoot ('build/' + $Mode)) (Join-Path $PSScriptRoot 'JHnode.spec')
    if ($LASTEXITCODE -ne 0) { throw 'JHnode EXE build failed.' }
    if ($Mode -eq 'single') {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'build_support/README-single.txt') -Destination (Join-Path $OutputDirectory 'JHnode-README.txt') -Force
        & $python (Join-Path $PSScriptRoot 'build_support/export_notices.py') --exe (Join-Path $OutputDirectory 'JHnode.exe') --output $OutputDirectory
        if ($LASTEXITCODE -ne 0) { throw 'Exporting bundled notices failed.' }
        Write-Host ('Built: ' + (Join-Path $OutputDirectory 'JHnode.exe'))
    } else {
        foreach ($name in @('README.txt', 'THIRD-PARTY-NOTICES.txt')) {
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot ('build_support/' + $name)) -Destination (Join-Path $OutputDirectory ('JHnode/' + $name)) -Force
        }
        Write-Host ('Built: ' + (Join-Path $OutputDirectory 'JHnode/JHnode.exe'))
    }
} finally {
    $env:JHNODE_BUILD_MODE = $oldMode
    if ($oldPath) { $env:PATH = $oldPath }
    Pop-Location
}
