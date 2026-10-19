param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$originalPath = $env:PATH
$Python = (& $Python -c "import sys; print(sys.executable)").Trim()
if ($LASTEXITCODE -ne 0) { throw "Não foi possível localizar o Python." }
# Avoid collecting DLLs from unrelated tools (for example another ICU build).
$env:PATH = @((Split-Path -Parent $Python), "$env:SystemRoot\System32", $env:SystemRoot) -join ";"
Push-Location $projectRoot
try {
    & $Python -m PyInstaller --noconfirm --clean --windowed --onedir `
        --name AstroPanel --paths src `
        --icon src/astropanel/resources/astropanel-icon.ico `
        --add-data "src/astropanel/resources;astropanel/resources" `
        run_astropanel.py
    if ($LASTEXITCODE -ne 0) { throw "Falha no empacotamento Windows." }
    Copy-Item -LiteralPath "tools/LEIA-ME-Windows.txt" -Destination "dist/AstroPanel/LEIA-ME.txt"
    $version = (& $Python -c "import sys; sys.path.insert(0, 'src'); from astropanel import __version__; print(__version__)").Trim()
    $archive = "dist/AstroPanel-$version-Windows-x64.zip"
    if (Test-Path -LiteralPath $archive) { throw "O pacote já existe: $archive" }
    Compress-Archive -LiteralPath "dist/AstroPanel" -DestinationPath $archive
    Write-Output "Pacote criado: $archive"
} finally {
    $env:PATH = $originalPath
    Pop-Location
}
