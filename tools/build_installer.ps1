param([string]$Python = "python", [string]$ISCC = "")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ISCC) {
    $candidates = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
    $ISCC = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $ISCC) { throw "Instale o Inno Setup 6 ou informe -ISCC com o caminho do compilador." }
}
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath 'dist/AstroPanel/_internal/python311.dll')) {
        throw "Gere primeiro o pacote Windows com tools/build_windows.ps1 usando Python 3.11."
    }
    $version = (& $Python -c "import sys; sys.path.insert(0, 'src'); from astropanel import __version__; print(__version__)").Trim()
    if ($LASTEXITCODE -ne 0) { throw "Falha ao consultar a versão." }
    & $ISCC "/DAppVersion=$version" "tools/AstroPanel.iss"
    if ($LASTEXITCODE -ne 0) { throw "Falha ao gerar o instalador." }
} finally {
    Pop-Location
}
