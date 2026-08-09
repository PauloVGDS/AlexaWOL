<#
.SYNOPSIS
    Verifica os requisitos do AlexaWOL e aponta o que precisa de atenção.

.DESCRIPTION
    Só lê o sistema — não altera nada. Rode antes de instalar, e de novo quando algo parar
    de funcionar.

    Nem tudo é verificável por script: BIOS, isolamento de clientes no roteador e a
    configuração da skill exigem conferência manual. O relatório diz o que ficou de fora.

    Compatível com Windows PowerShell 5.1 e PowerShell 7.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\check_requisitos.ps1
#>
[CmdletBinding()]
param(
    # Pula as verificações que dependem de rede/AWS, para uso offline.
    [switch]$Offline
)

$script:Falhas = 0
$script:Avisos = 0

function Secao($titulo) { Write-Host "`n$titulo" -ForegroundColor Cyan }

function Resultado($nivel, $rotulo, $detalhe) {
    switch ($nivel) {
        'ok'    { Write-Host "  [ OK ]   " -ForegroundColor Green -NoNewline }
        'aviso' { Write-Host "  [AVISO]  " -ForegroundColor Yellow -NoNewline; $script:Avisos++ }
        'falha' { Write-Host "  [FALHA]  " -ForegroundColor Red -NoNewline; $script:Falhas++ }
        'info'  { Write-Host "  [ -- ]   " -ForegroundColor DarkGray -NoNewline }
    }
    Write-Host $rotulo -NoNewline
    if ($detalhe) { Write-Host "  $detalhe" -ForegroundColor DarkGray } else { Write-Host "" }
}

Write-Host "AlexaWOL — verificacao de requisitos" -ForegroundColor White

# ---------------------------------------------------------------- Sistema
Secao 'Sistema'

$os = Get-CimInstance Win32_OperatingSystem
if ($os.Caption -match 'Windows 1[01]') {
    Resultado ok 'Windows 10 ou 11' $os.Caption
} else {
    Resultado aviso 'Versao do Windows nao testada' $os.Caption
}

Resultado info 'PowerShell' ("$($PSVersionTable.PSVersion)  " + $(if ($PSVersionTable.PSVersion.Major -ge 7) { '(sem o problema de BOM)' } else { '(5.1: use a escrita sem BOM dos guias)' }))

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
         ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($admin) {
    Resultado ok 'Sessao elevada' 'todos os .ps1 do projeto vao rodar sem restricao'
} else {
    Resultado falha 'Sessao NAO elevada' 'abra o PowerShell como Administrador — install_task.ps1 e as mudancas de energia do adaptador exigem'
}

# ---------------------------------------------------------------- Python
Secao 'Python e dependencias'

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Resultado falha 'python nao esta no PATH' 'instale o Python 3.11+ marcando "Add to PATH"'
} else {
    $ver = (& python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null)
    $maj, $min = $ver -split '\.'
    if ([int]$maj -gt 3 -or ([int]$maj -eq 3 -and [int]$min -ge 11)) {
        Resultado ok "Python $ver" $py.Source
    } else {
        Resultado falha "Python $ver e antigo demais" 'o agente usa tomllib, que exige 3.11+'
    }

    $pkgs = @{ 'paho.mqtt' = 'paho-mqtt'; 'comtypes' = 'comtypes'; 'pycaw' = 'pycaw' }
    foreach ($mod in $pkgs.Keys) {
        & python -c "import $mod" 2>$null
        if ($LASTEXITCODE -eq 0) { Resultado ok "modulo $($pkgs[$mod])" }
        else { Resultado falha "falta o modulo $($pkgs[$mod])" 'python -m pip install -r agent\requirements.txt' }
    }

    # A API do pycaw mudou: AudioDevice.EndpointVolume substituiu Activate().
    & python -c "from pycaw.pycaw import AudioUtilities; AudioUtilities.GetSpeakers().EndpointVolume" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $dev = & python -c "from pycaw.pycaw import AudioUtilities; print(AudioUtilities.GetSpeakers().FriendlyName)" 2>$null
        Resultado ok 'Core Audio acessivel' "saida padrao: $dev"
    } else {
        Resultado falha 'nao consegui ler o volume' 'pycaw antigo (<20251023) ou nenhum dispositivo de audio ativo'
    }
}

# ---------------------------------------------------------------- Rede local
Secao 'Rede e Wake-on-LAN'

$nics = Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.Virtual -eq $false }
$cabeada = $nics | Where-Object { $_.PhysicalMediaType -notmatch 'Wireless|802.11' } | Select-Object -First 1

if (-not $cabeada) {
    Resultado falha 'nenhuma interface cabeada ativa' 'WOL por Wi-Fi e pouco confiavel; o resto do projeto funciona'
} else {
    Resultado ok "interface cabeada: $($cabeada.Name)" "MAC $($cabeada.MacAddress) — use este no PC_MAC"

    try {
        $adv = Get-NetAdapterAdvancedProperty -Name $cabeada.Name -ErrorAction Stop
        foreach ($alvo in @('Wake on Magic Packet', 'Shutdown Wake-On-Lan')) {
            $p = $adv | Where-Object DisplayName -eq $alvo
            if (-not $p) { Resultado aviso "'$alvo' nao existe no driver" 'o nome varia por fabricante; confira no BIOS' }
            elseif ($p.DisplayValue -match 'Enabled|Ativado|Habilitado') { Resultado ok "'$alvo' habilitado" }
            else { Resultado falha "'$alvo' esta '$($p.DisplayValue)'" 'habilite nas propriedades avancadas do adaptador' }
        }
    } catch {
        Resultado aviso 'nao consegui ler as propriedades do adaptador' $_.Exception.Message
    }

    $armed = (powercfg /devicequery wake_armed) -join "`n"
    if ($armed -match [regex]::Escape($cabeada.InterfaceDescription)) {
        Resultado ok 'placa autorizada a acordar o PC'
    } else {
        Resultado falha 'placa NAO esta em wake_armed' 'Gerenciador de Dispositivos > adaptador > Energia'
    }
}

$hiberboot = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power' -ErrorAction SilentlyContinue).HiberbootEnabled
if ($null -eq $hiberboot) { Resultado info 'Fast Startup nao encontrado no registro' }
elseif ($hiberboot -eq 0) { Resultado ok 'Fast Startup desativado' 'necessario para acordar do desligamento' }
else { Resultado falha 'Fast Startup ATIVADO' 'quebra o WOL a partir do S5 — desative nas Opcoes de Energia' }

$sleep = (powercfg /availablesleepstates) -join "`n"
if ($sleep -match 'Espera \(S3\)|Standby \(S3\)') { Resultado ok 'S3 disponivel' }
else { Resultado aviso 'S3 indisponivel' 'suspender pode virar hibernacao — nao impede o WOL' }

# --------------------------------------------------- Echo na mesma sub-rede
if (-not $Offline) {
    Secao 'Echo na rede local'

    $meuIp = Get-NetIPAddress -AddressFamily IPv4 -InterfaceIndex $cabeada.ifIndex -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if ($meuIp) {
        $prefixo = ($meuIp.IPAddress -split '\.')[0..2] -join '.'
        Resultado info 'sub-rede do PC' "$($meuIp.IPAddress)/$($meuIp.PrefixLength)"

        # A tabela ARP expira, entao um dispositivo ligado pode simplesmente nao estar nela.
        # Uma varredura rapida de ping popula a tabela antes de consultarmos.
        Write-Host "  ...varrendo a sub-rede para popular a tabela ARP" -ForegroundColor DarkGray
        $pings = 1..254 | ForEach-Object {
            (New-Object System.Net.NetworkInformation.Ping).SendPingAsync("$prefixo.$_", 400)
        }
        [Threading.Tasks.Task]::WaitAll($pings, 3000) | Out-Null

        # OUIs da Amazon. Lista parcial — a ausencia nao prova que a Echo esta em outra rede.
        $amazon = @('50:07:C3','44:65:0D','68:37:E9','F0:27:2D','74:C2:46','0C:47:C9','40:B4:CD',
                    'AC:63:BE','FC:65:DE','84:D6:D0','B4:7C:9C','A0:02:DC','08:7C:39')
        $viz = Get-NetNeighbor -AddressFamily IPv4 -ErrorAction SilentlyContinue |
               Where-Object { $_.IPAddress -like "$prefixo.*" -and $_.State -in 'Reachable','Stale' }
        $echos = $viz | Where-Object {
            $oui = ($_.LinkLayerAddress -replace '-', ':').Substring(0, 8)
            $amazon -contains $oui
        }
        if ($echos) {
            foreach ($e in $echos) { Resultado ok 'dispositivo Amazon na mesma sub-rede' $e.IPAddress }
        } else {
            # Deliberadamente 'info', nao 'aviso': a deteccao e por OUI e a lista e parcial,
            # entao a ausencia nao prova nada. Confirme pelo app.
            Resultado info 'nenhum dispositivo Amazon detectado' 'pode estar desligado ou com OUI fora da lista — confira o IP da Echo no app Alexa e compare o prefixo'
        }
    }
}

# ---------------------------------------------------------------- Nuvem
if (-not $Offline) {
    Secao 'Ferramentas de nuvem'

    $awsCmd = Get-Command aws -ErrorAction SilentlyContinue
    if (-not $awsCmd) {
        Resultado aviso 'aws CLI nao esta no PATH' 'necessario para publicar o Lambda; da para usar o console web'
    } else {
        $v = (& aws --version 2>&1)
        if ($v -match 'aws-cli/2') { Resultado ok 'aws CLI v2' $v }
        else { Resultado aviso 'aws CLI v1' 'os guias usam --cli-binary-format, que exige a v2' }

        $ident = (& aws sts get-caller-identity --output json 2>&1)
        if ($LASTEXITCODE -eq 0) {
            $arn = ($ident | ConvertFrom-Json).Arn
            Resultado ok 'credenciais AWS funcionando' $arn
        } else {
            Resultado aviso 'credenciais AWS nao configuradas' 'aws configure'
        }
    }
}

# ---------------------------------------------------------------- Config
Secao 'Configuracao do agente'

$cfg = Join-Path $env:LOCALAPPDATA 'AlexaWOL\config.toml'
if (-not (Test-Path $cfg)) {
    Resultado info 'config.toml ainda nao existe' "sera criado em $cfg"
} else {
    Resultado ok 'config.toml encontrado' $cfg
    # So linhas de atribuicao — o cabecalho do arquivo menciona TROQUE-ME num comentario, e
    # casar com ele daria falso positivo permanente.
    $pendentes = Get-Content $cfg | Where-Object { $_ -match '^\s*[\w_]+\s*=' -and $_ -match 'TROQUE-ME' }
    if ($pendentes) {
        Resultado aviso "$($pendentes.Count) campo(s) com TROQUE-ME" (($pendentes | ForEach-Object { ($_ -split '=')[0].Trim() }) -join ', ')
    } else {
        Resultado ok 'sem campos pendentes'
    }
}

$legado = Join-Path (Split-Path $PSScriptRoot -Parent) 'agent\config.toml'
if (Test-Path $legado) {
    Resultado falha 'config.toml dentro do projeto' 'se o repo estiver em pasta sincronizada, seus segredos vao para a nuvem — mova para %LOCALAPPDATA%\AlexaWOL'
}

$raiz = Split-Path $PSScriptRoot -Parent
foreach ($svc in @('OneDrive', 'Dropbox', 'Google Drive', 'iCloudDrive')) {
    if ($raiz -like "*\$svc\*") {
        Resultado aviso "o projeto esta dentro do $svc" 'o .git sincronizado pode corromper se aberto em duas maquinas'
    }
}

$tarefa = Get-ScheduledTask -TaskName 'AlexaWOL Agent' -ErrorAction SilentlyContinue
if ($tarefa) {
    $proc = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" -ErrorAction SilentlyContinue
    Resultado ok "tarefa registrada (State: $($tarefa.State))" $(if ($proc) { "processo vivo: PID $($proc[0].ProcessId)" } else { 'nenhum pythonw rodando' })
} else {
    Resultado info 'tarefa agendada ainda nao registrada' 'agent\install_task.ps1'
}

# ---------------------------------------------------------------- Fecho
Secao 'Nao verificavel por script — confira manualmente'
Write-Host "  BIOS  " -ForegroundColor Yellow -NoNewline
Write-Host "REQUISITO, nao sugestao. 'Power On by PCI-E' habilitado e 'ErP Ready'"
Write-Host "        DESABILITADO. A configuracao de fabrica da maioria das placas corta a"
Write-Host "        energia da rede no desligamento, e ai nenhum ajuste do Windows resolve."
Write-Host "  Roteador: isolamento de clientes desligado" -ForegroundColor DarkGray
Write-Host "  Alexa: skill na MESMA conta da Echo, toggle Send Alexa Events" -ForegroundColor DarkGray
Write-Host "  O teste real de WOL exige outro aparelho — veja docs\setup-wol.md" -ForegroundColor DarkGray

Write-Host ""
if ($script:Falhas -gt 0) {
    Write-Host "$($script:Falhas) falha(s) e $($script:Avisos) aviso(s)." -ForegroundColor Red
    exit 1
} elseif ($script:Avisos -gt 0) {
    Write-Host "Sem falhas, $($script:Avisos) aviso(s) para conferir." -ForegroundColor Yellow
    exit 0
} else {
    Write-Host "Tudo certo." -ForegroundColor Green
    exit 0
}
