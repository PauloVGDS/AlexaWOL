<#
.SYNOPSIS
    Prepara o lado do PC: dependências, config.toml e segredo HMAC.

.DESCRIPTION
    Automatiza o que dá para automatizar sem sair da máquina. NÃO cria a conta do HiveMQ, o
    perfil Login with Amazon nem a skill — todos exigem navegador e login interativo.

    É idempotente: rodar de novo não sobrescreve um config.toml existente.

    Depois deste script, o caminho é:
      1. preencher as credenciais do HiveMQ no config.toml (docs\setup-hivemq.md)
      2. agent\install_task.ps1 para registrar o serviço
      3. docs\setup-aws.md e docs\setup-alexa.md para o lado da nuvem

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\setup_local.ps1
#>
[CmdletBinding()]
param(
    # Gera um segredo HMAC novo mesmo que o config já exista. Lembre de atualizar o
    # HMAC_SECRET do Lambda junto — se divergirem, todo comando é recusado.
    [switch]$NovoSegredo
)

$ErrorActionPreference = 'Stop'
$repo    = Split-Path $PSScriptRoot -Parent
$destino = Join-Path $env:LOCALAPPDATA 'AlexaWOL'
$config  = Join-Path $destino 'config.toml'
$exemplo = Join-Path $repo 'agent\config.example.toml'

function Passo($texto) { Write-Host "`n> $texto" -ForegroundColor Cyan }

# ------------------------------------------------------------ 1. Dependências
Passo 'Instalando dependências do agente'

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw 'python nao esta no PATH. Instale o Python 3.11+ marcando "Add python.exe to PATH".' }

$ver = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
$maj, $min = $ver -split '\.'
if ([int]$maj -lt 3 -or ([int]$maj -eq 3 -and [int]$min -lt 11)) {
    throw "Python $ver e antigo demais — o agente usa tomllib, que exige 3.11+."
}
Write-Host "  Python $ver em $($py.Source)"

& python -m pip install --quiet --upgrade -r (Join-Path $repo 'agent\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install falhou' }
Write-Host '  dependencias instaladas'

# ------------------------------------------------------------ 2. Diretório
Passo "Preparando $destino"

if (-not (Test-Path $destino)) {
    New-Item -ItemType Directory -Path $destino | Out-Null
    Write-Host '  diretorio criado'
} else {
    Write-Host '  diretorio ja existia'
}

# Fora da árvore do projeto de propósito: se o repo estiver em pasta sincronizada, um
# config.toml ali dentro sobe para a nuvem com as credenciais e o segredo HMAC.
foreach ($svc in @('OneDrive', 'Dropbox', 'Google Drive', 'iCloudDrive')) {
    if ($repo -like "*\$svc\*") {
        Write-Host "  nota: o projeto esta dentro do $svc — por isso o config vai para %LOCALAPPDATA%" -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------ 3. config.toml
Passo 'Configuracao'

if (Test-Path $config) {
    Write-Host "  config.toml ja existe — preservado" -ForegroundColor Yellow
    Write-Host "  (apague o arquivo e rode de novo para recriar do zero)"
} else {
    Copy-Item $exemplo $config
    Write-Host "  criado a partir de config.example.toml"
}

# Segredo HMAC — o mesmo valor precisa ir para a variavel HMAC_SECRET do Lambda.
$texto = Get-Content $config -Raw
$temPlaceholder = $texto -match '(?m)^\s*secret\s*=\s*"TROQUE-ME"'

if ($temPlaceholder -or $NovoSegredo) {
    $segredo = & python -c "import secrets; print(secrets.token_hex(32))"
    $texto = $texto -replace '(?m)^(\s*secret\s*=\s*)".*"', "`${1}`"$segredo`""
    [System.IO.File]::WriteAllText($config, $texto, (New-Object System.Text.UTF8Encoding $false))
    Write-Host '  segredo HMAC gerado (64 caracteres hex)'
    Write-Host '  IMPORTANTE: use o MESMO valor na variavel HMAC_SECRET do Lambda' -ForegroundColor Yellow
} else {
    Write-Host '  segredo HMAC ja definido — preservado'
}

# ------------------------------------------------------------ 4. O que falta
Passo 'O que ainda precisa de voce'

$pendentes = Get-Content $config | Where-Object { $_ -match '^\s*[\w_]+\s*=' -and $_ -match 'TROQUE-ME' }
if ($pendentes) {
    Write-Host '  campos a preencher no config.toml:' -ForegroundColor Yellow
    foreach ($p in $pendentes) { Write-Host "    - $(($p -split '=')[0].Trim())" }
    Write-Host "  arquivo: $config"
    Write-Host '  valores: crie o cluster em docs\setup-hivemq.md'
} else {
    Write-Host '  config.toml esta completo'
}

Write-Host ''
Write-Host 'Nao automatizavel (exige navegador e login):' -ForegroundColor DarkGray
Write-Host '  - cluster e credenciais do HiveMQ    docs\setup-hivemq.md' -ForegroundColor DarkGray
Write-Host '  - perfil Login with Amazon           docs\setup-alexa.md' -ForegroundColor DarkGray
Write-Host '  - criacao da skill e account linking docs\setup-alexa.md' -ForegroundColor DarkGray
Write-Host ''
Write-Host 'Proximo passo depois de preencher o config:' -ForegroundColor Cyan
Write-Host '  powershell -ExecutionPolicy Bypass -File tools\check_requisitos.ps1'
Write-Host '  powershell -ExecutionPolicy Bypass -File agent\install_task.ps1'
