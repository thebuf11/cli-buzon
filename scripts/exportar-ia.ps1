<#
.SYNOPSIS
    Copia las variables CENTRO_IA_* del .env a las variables de usuario de Windows.

.DESCRIPTION
    OpenCode y buzon usan las mismas variables (CENTRO_IA_URL, CENTRO_IA_KEY,
    CENTRO_IA_CA y CENTRO_IA_MODELO). OpenCode no lee el .env, así que este
    script las guarda como variables de usuario: valen para cualquier terminal
    nueva, para OpenCode y para buzon desde cualquier carpeta.

    También define NODE_EXTRA_CA_CERTS con el certificado del centro, que es lo
    que necesita OpenCode (Node) para fiarse del servidor.

    Nunca muestra los valores: solo dice qué variable se ha guardado.

.EXAMPLE
    .\scripts\exportar-ia.ps1
    .\scripts\exportar-ia.ps1 -Fichero "$env:APPDATA\buzon\.env"
#>
param(
    [string]$Fichero = (Join-Path $PSScriptRoot "..\.env")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Fichero)) {
    Write-Host "No encuentro $Fichero. Copia .env.example a .env y rellena la IA del centro." -ForegroundColor Red
    exit 1
}

$valores = @{}
foreach ($linea in Get-Content -LiteralPath $Fichero -Encoding UTF8) {
    if ($linea -match '^\s*(CENTRO_IA_[A-Z_]+)\s*=(.*)$') {
        $valor = $Matches[2].Trim().Trim('"').Trim("'")
        if ($valor) { $valores[$Matches[1]] = $valor }
    }
}

if (-not $valores.ContainsKey("CENTRO_IA_URL") -or -not $valores.ContainsKey("CENTRO_IA_KEY")) {
    Write-Host "Rellena al menos CENTRO_IA_URL y CENTRO_IA_KEY en $Fichero y vuelve a ejecutarlo." -ForegroundColor Yellow
    exit 1
}

# Node y OpenCode no entienden «~»: se guarda la ruta completa del certificado.
if ($valores.ContainsKey("CENTRO_IA_CA")) {
    $ca = $valores["CENTRO_IA_CA"] -replace '^~', $HOME
    if (-not (Test-Path -LiteralPath $ca -PathType Leaf)) {
        Write-Host "CENTRO_IA_CA apunta a un fichero que no existe: $ca" -ForegroundColor Red
        exit 1
    }
    $ca = (Resolve-Path -LiteralPath $ca).Path
    $valores["CENTRO_IA_CA"] = $ca
    $valores["NODE_EXTRA_CA_CERTS"] = $ca
}

foreach ($nombre in ($valores.Keys | Sort-Object)) {
    [Environment]::SetEnvironmentVariable($nombre, $valores[$nombre], "User")
    Set-Item -Path "Env:$nombre" -Value $valores[$nombre]  # también en esta terminal
    Write-Host "Guardada $nombre" -ForegroundColor Green
}

Write-Host ""
Write-Host "Listo. Abre una terminal nueva para que OpenCode las vea, y prueba: buzon comprobar-ia"
Write-Host "Para quitarlas: [Environment]::SetEnvironmentVariable('CENTRO_IA_KEY', `$null, 'User') (una por variable)."
