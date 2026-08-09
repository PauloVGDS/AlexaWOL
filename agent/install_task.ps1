<#
.SYNOPSIS
    Registra o agente AlexaWOL como Tarefa Agendada, iniciando no logon.

.DESCRIPTION
    Roda na SESSÃO DO USUÁRIO, e não como SYSTEM, de propósito: o Core Audio do Windows é
    isolado na sessão 0, então um serviço SYSTEM não consegue mexer no volume.

    Isso não é limitação prática. Ao acordar do S3 a sessão do usuário continua viva (ainda
    que bloqueada) e o agente segue rodando. E "ligar" nunca depende do agente — quem
    transmite o magic packet é a Echo.

    Usa pythonw.exe para não abrir janela de console.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File install_task.ps1
    powershell -ExecutionPolicy Bypass -File install_task.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [string]$TaskName = 'AlexaWOL Agent',
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$agentDir = $PSScriptRoot
$script   = Join-Path $agentDir 'alexawol_agent.py'
# Fora da arvore do projeto de proposito: se o projeto estiver em OneDrive/Dropbox, um
# config.toml ali dentro seria sincronizado para a nuvem com as credenciais e o segredo HMAC.
$config   = Join-Path $env:LOCALAPPDATA 'AlexaWOL\config.toml'
$legacy   = Join-Path $agentDir 'config.toml'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Tarefa '$TaskName' removida."
    } else {
        Write-Host "Tarefa '$TaskName' não existe."
    }
    return
}

if (-not (Test-Path $script)) { throw "Não encontrei o agente em $script" }

if (-not (Test-Path $config)) {
    if (Test-Path $legacy) {
        throw @"
O config.toml está em $legacy, dentro da árvore do projeto.
Se o projeto estiver em OneDrive/Dropbox, esse arquivo — que guarda as duas credenciais MQTT
e o segredo HMAC — está sendo sincronizado para a nuvem. Mova para fora:

    New-Item -ItemType Directory -Force (Split-Path '$config') | Out-Null
    Move-Item '$legacy' '$config'
"@
    }
    throw "Falta o config.toml em $config. Copie agent\config.example.toml para lá e preencha."
}

# pythonw.exe roda sem console. Derivamos do python do PATH para respeitar venv.
$pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) { throw 'python não encontrado no PATH.' }
$pythonw = Join-Path (Split-Path $pythonExe) 'pythonw.exe'
if (-not (Test-Path $pythonw)) {
    Write-Warning "pythonw.exe não encontrado; usando python.exe (vai abrir uma janela de console)."
    $pythonw = $pythonExe
}

$action = New-ScheduledTaskAction -Execute $pythonw `
    -Argument ('"{0}"' -f $script) -WorkingDirectory $agentDir

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

# Sem limite de tempo e sem parar em bateria — é um serviço de longa duração.
# Reinicia sozinho se morrer, por exemplo numa queda longa de rede.
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Highest

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal `
    -Description 'Escuta comandos da Alexa via MQTT e controla volume/energia do PC.' | Out-Null

Write-Host "Tarefa '$TaskName' registrada."
Write-Host "Iniciar agora:  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Ver estado:     Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo"
