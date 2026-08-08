<#
.SYNOPSIS
    Empacota o Lambda em um zip pronto para deploy.

.DESCRIPTION
    Junta o código da função, o pacote `shared/` da raiz do repositório e as dependências
    do requirements.txt. O boto3 já existe no runtime da AWS, então não vai no pacote.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File build.ps1
    powershell -ExecutionPolicy Bypass -File build.ps1 -Deploy -FunctionName alexawol
#>
[CmdletBinding()]
param(
    [switch]$Deploy,
    [string]$FunctionName = 'alexawol',
    [string]$Region = 'us-east-1'
)

$ErrorActionPreference = 'Stop'
$lambdaDir = $PSScriptRoot
$repoRoot  = Split-Path $lambdaDir -Parent
$buildDir  = Join-Path $lambdaDir 'build'
$zipPath   = Join-Path $lambdaDir 'alexawol.zip'

if (Test-Path $buildDir) { Remove-Item $buildDir -Recurse -Force }
if (Test-Path $zipPath)  { Remove-Item $zipPath -Force }
New-Item -ItemType Directory -Path $buildDir | Out-Null

Write-Host 'Copiando o código da função...'
Copy-Item (Join-Path $lambdaDir 'lambda_function.py') $buildDir
Copy-Item (Join-Path $lambdaDir 'config.py')          $buildDir
Copy-Item (Join-Path $lambdaDir 'alexa')  $buildDir -Recurse
Copy-Item (Join-Path $lambdaDir 'bridge') $buildDir -Recurse

# shared/ é compartilhado com o agente; entra no zip para o Lambda enxergar como pacote.
Write-Host 'Copiando shared/...'
Copy-Item (Join-Path $repoRoot 'shared') $buildDir -Recurse

Write-Host 'Instalando dependências...'
python -m pip install --quiet --upgrade `
    --target $buildDir `
    -r (Join-Path $lambdaDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install falhou' }

# Caches de bytecode só incham o pacote.
Get-ChildItem $buildDir -Recurse -Directory -Filter '__pycache__' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host 'Compactando...'
Compress-Archive -Path (Join-Path $buildDir '*') -DestinationPath $zipPath -Force

$sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 2)
Write-Host "Pronto: $zipPath ($sizeMb MB)"

if ($Deploy) {
    Write-Host "Publicando em $FunctionName ($Region)..."
    aws lambda update-function-code `
        --function-name $FunctionName `
        --zip-file "fileb://$zipPath" `
        --region $Region `
        --output json
    if ($LASTEXITCODE -ne 0) { throw 'update-function-code falhou' }
    Write-Host 'Deploy concluído.'
}
