# Requisitos e o que varia entre máquinas

Este projeto foi validado numa configuração específica. Boa parte do que funcionou aqui
depende de premissas que **não valem para todo mundo** — e várias delas falham em silêncio.

Este documento lista o que precisa ser verdade, o que costuma diferir, e como descobrir o seu
caso antes de perder tempo depurando.

## Requisitos mínimos

| Item | Exigência | Por quê |
|---|---|---|
| Windows | 10 ou 11 | `pycaw`, teclas de mídia e Tarefas Agendadas |
| Python no PC | **3.11+** | O agente usa `tomllib`, que só existe a partir do 3.11 |
| Rede do PC | **cabeada** | Wake-on-LAN por Wi-Fi é pouco confiável (ver abaixo) |
| Echo | mesma **sub-rede** do PC | Requisito oficial da Amazon para o WOL |
| Conta AWS | qualquer, com Lambda | Cabe no always-free (1M req/mês) |
| Conta de desenvolvedor Alexa | a **mesma** da Echo | Skill em modo dev só habilita nessa conta |
| PowerShell | 5.1 serve, 7 é melhor | Diferença de codificação, ver [problemas](problemas-encontrados.md) |

Descobrir a versão do Python:

```powershell
python --version
```

Com 3.10 ou anterior, o agente nem inicia. A saída é atualizar o Python ou trocar `tomllib`
por `tomli` — uma linha, mas não está feita.

---

## Idioma da skill → região da AWS

**A armadilha mais provável para quem não fala português.** A região do Lambda **não é
escolha** — é determinada pelo idioma da skill, e usar a errada faz a Alexa simplesmente nunca
invocar a função. Nenhum erro aparece em lugar nenhum.

| Idioma da skill | Região do Lambda | Event gateway |
|---|---|---|
| Português (BR), Inglês (US/CA), Espanhol (MX/US), Francês (CA), Árabe (SA) | `us-east-1` | `https://api.amazonalexa.com/v3/events` |
| Inglês (UK/IN), Alemão, Francês (FR), Italiano, Espanhol (ES), Holandês, Híndi | `eu-west-1` | `https://api.eu.amazonalexa.com/v3/events` |
| Inglês (AU), Japonês | `us-west-2` | `https://api.fe.amazonalexa.com/v3/events` |

O gateway é configurável pela variável de ambiente `EVENT_GATEWAY` do Lambda; o padrão é o da
América do Norte. Se a sua skill não for de um idioma da primeira linha, **você precisa mudar
as duas coisas** — região e gateway. Confirme na documentação da Amazon antes, porque esse
mapeamento já mudou no passado.

Os comandos nos guias usam `--region us-east-1` explícito por causa disso. Troque em todos se
o seu idioma for outro.

---

## Hardware e BIOS

### A placa de rede precisa acordar a máquina

Verifique:

```powershell
Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name, MacAddress, LinkSpeed
Get-NetAdapterAdvancedProperty -Name '<sua interface>' | Where-Object DisplayName -match 'Wake|Shutdown'
powercfg /devicequery wake_armed
```

**Os nomes das propriedades variam por fabricante.** Aqui, numa Realtek, aparecem como
`Wake on Magic Packet` e `Shutdown Wake-On-Lan`. Em Intel costuma ser `Wake on Magic Packet` e
`PME`; em Killer e alguns notebooks, a opção pode nem existir na interface do driver. Se você
não encontrar nada parecido, o caminho é o BIOS.

### Wi-Fi normalmente não serve

WoWLAN existe, mas depende do adaptador, do driver e do roteador — e na maioria das
combinações não funciona com a máquina desligada. Se o seu PC só tem Wi-Fi, trate o "ligar"
como improvável e o resto do projeto como perfeitamente utilizável.

### Fast Startup quebra o WOL a partir do desligamento

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Power').HiberbootEnabled
```

Precisa ser `0`. É a causa mais comum de "acorda quando suspendo, não acorda quando desligo".
Desativar: Painel de Controle → Opções de Energia → Escolher a função dos botões → Alterar
configurações não disponíveis → desmarcar "Ligar inicialização rápida".

### BIOS

Se o WOL funciona do S3 mas não do S5, é aqui. Procure por:

- **Power On by PCI-E / PCI** → Enabled
- **Wake on LAN / Resume by LAN** → Enabled
- **ErP Ready / EuP** → **Disabled** — corta a energia da placa de rede no S5; é o culpado
  mais frequente e o nome não menciona rede
- **Deep Sleep / Deep Sx** → Disabled

### Suspender pode virar hibernar

Nesta máquina, `SetSuspendState` entra em S3 de verdade mesmo com hibernação ativa —
confirmado pelos eventos 42/107 do log do sistema. **Isso depende de firmware e drivers.** Em
outra máquina pode cair em S4. Na prática o WOL funciona nos dois estados desde que a placa
esteja armada, então normalmente não importa. Se importar, `powercfg -h off`.

Conferir o que aconteceu:

```powershell
Get-WinEvent -LogName System -MaxEvents 20 | Where-Object Id -in 42,107 |
    Select-Object TimeCreated, Id
```

---

## Rede

### A Echo precisa estar na mesma sub-rede

Requisito oficial, e o que mais quebra em casas com rede moderna:

- **Rede de convidados** para dispositivos IoT — sub-rede diferente, não funciona
- **Wi-Fi mesh com SSID separado por banda** — pode virar sub-rede distinta conforme o modelo
- **VLANs** — mesmo caso
- **AP isolation / isolamento de clientes** — bloqueia broadcast entre Wi-Fi e cabo, ainda que
  a sub-rede seja a mesma

Descobrir os dois endereços:

```powershell
Get-NetIPAddress -AddressFamily IPv4 | Where-Object InterfaceAlias -notmatch 'Loopback'
```

O da Echo está no app Alexa, em Dispositivos → sua Echo → Sobre. Os dois precisam ter o mesmo
prefixo de rede.

### Teste isolado antes de tudo

Antes de escrever qualquer configuração, confirme que a máquina acorda com um magic packet
vindo de outro aparelho da rede. Ver [setup-wol.md](setup-wol.md) — inclusive o caminho pelo
roteador, que muitos modelos têm embutido e dispensa instalar nada.

---

## Windows

### O volume vai para o dispositivo padrão

O agente age sobre o **dispositivo de saída padrão do momento**, buscado a cada comando. Se o
seu padrão for um fone Bluetooth ou a saída HDMI da TV, é lá que o volume muda — não nas
caixas.

Conferir qual é:

```powershell
python -c "from pycaw.pycaw import AudioUtilities; print(AudioUtilities.GetSpeakers().FriendlyName)"
```

**Sem nenhum dispositivo de áudio ativo, o agente falha ao ler o estado.** Acontece em máquinas
sem placa de som habilitada, em sessões RDP e em alguns servidores.

### A versão do pycaw importa

A API mudou. Versões anteriores a `20251023` usavam `speakers.Activate(...)`, que não existe
mais — e é o padrão que aparece em praticamente todo tutorial na internet. O
`requirements.txt` já fixa o mínimo, mas se você instalar por outro caminho, confira.

### Teclas de mídia dependem do player

Avançar e voltar faixa funcionam porque Spotify, YouTube e VLC registram o atalho global de
mídia. **Um player que não registra simplesmente ignora.** Não há erro: o agente emite a tecla
e nada acontece.

O Spotify instalado pela Microsoft Store foi validado aqui e funciona, inclusive o protocolo
`spotify:` para abrir uma faixa.

### O agente roda na sessão do usuário, não como serviço

Obrigatório: o Core Audio é isolado na sessão 0, e um serviço SYSTEM não enxerga o volume. A
consequência prática é que **o agente só existe depois do logon**. Numa máquina que fica na
tela de bloqueio esperando senha após ligar, ele nunca conecta — e comandos de volume ou
desligar caem no vazio.

Se você quer usar o "ligar" seguido de outro comando numa rotina, meça o tempo real de boot +
logon da sua máquina antes de fixar a espera.

### Privilégios

`install_task.ps1` registra a tarefa com `RunLevel Highest`. Numa conta sem direitos
administrativos isso falha. Rodar sem elevação funciona para volume e mídia; para
`shutdown /f` pode não bastar, dependendo da política local.

---

## Terminal

Duas diferenças que produzem erros sem relação aparente com a causa:

**Git Bash converte caminhos iniciados com `/`.** `aws ssm get-parameter --name /alexawol/...`
chega deformado e retorna `ParameterNotFound` para um parâmetro que existe. Use PowerShell para
qualquer argumento nesse formato.

**PowerShell 5.1 grava BOM com `Out-File -Encoding utf8`**, e a AWS CLI rejeita o JSON com
`Unexpected UTF-8 BOM`. O PowerShell 7 não. Como os dois convivem na mesma máquina, o erro
aparece ou não conforme o terminal aberto. Os guias já usam a escrita explícita sem BOM.

Ambos estão detalhados em [problemas-encontrados.md](problemas-encontrados.md).

---

## Nuvem

### Modelo da Echo

A interface `WakeOnLANController` exige um dispositivo Alexa capaz de transmitir o magic
packet. A lista oficial da Amazon está desatualizada, mas cobre "Echo Show (all generations)",
"Echo (all generations)" e "Echo Dot (all generations)". Modelos muito antigos — Echo de 1ª
geração — perderam capacidades de rede local em atualizações de firmware. Se você só tem um
Echo de 1ª geração, valide cedo.

### Free tier da AWS

A AWS reestruturou o free tier em julho de 2025. Contas novas escolhem entre um plano gratuito
que **encerra em 6 meses** e um plano pago. O always-free do Lambda (1M requisições/mês)
persiste nos dois, então o gasto real deste projeto continua zero — mas o cadastro pede cartão.

### HiveMQ

O plano Serverless gratuito dá 100 conexões e 10 GB/mês, muito acima do consumo daqui, e não
expira por inatividade. Se você preferir outro broker MQTT, o agente e o Lambda só precisam de
host, porta, usuário e senha — não há nada específico do HiveMQ no código.

---

## O que dá para automatizar

```powershell
powershell -ExecutionPolicy Bypass -File tools\check_requisitos.ps1
powershell -ExecutionPolicy Bypass -File tools\setup_local.ps1
```

O primeiro **só lê** o sistema e não altera nada. O segundo instala dependências, cria o
`config.toml` em `%LOCALAPPDATA%` e gera o segredo HMAC — é idempotente, então rodar de novo
não sobrescreve o que já existe.

### O que o verificador cobre sozinho

Versão do Windows e do PowerShell, elevação da sessão, versão do Python, presença de cada
dependência, leitura real do Core Audio (que é o teste que pega o `pycaw` antigo), interface
cabeada e MAC, as propriedades de Wake-on-LAN do driver, `wake_armed`, Fast Startup, estados de
suspensão, presença da AWS CLI e validade das credenciais, estado do `config.toml` e da tarefa
agendada.

Também varre a sub-rede para detectar a Echo pelo OUI do MAC. A varredura popula a tabela ARP
antes de consultar — sem isso, um dispositivo ligado simplesmente não aparece, porque as
entradas expiram.

### O que não dá, e por quê

| Não automatizável | Motivo |
|---|---|
| BIOS (ErP, Power On by PCI-E) | Não há API para ler ou escrever essas opções |
| Isolamento de clientes no roteador | Depende do modelo; não há interface padrão |
| Cluster e credenciais do HiveMQ | Console web, sem API pública no plano gratuito |
| Perfil Login with Amazon | Exige login interativo no navegador |
| Criação da skill e account linking | Idem; o ASK CLI cobre parte, mas ainda pede login |
| Toggle **Send Alexa Events** | Só existe no console da skill |
| O teste real de WOL | Precisa de um segundo aparelho na rede |

A detecção da Echo é **best-effort**: identifica pelo OUI, e a lista é parcial. Não encontrar
não prova que ela está em outra sub-rede — por isso o script reporta como informação, não como
falha.

### O lado da AWS

`lambda\build.ps1 -Deploy` já empacota e publica. A criação inicial — papel IAM, função,
variáveis de ambiente e `add-permission` — está em [setup-aws.md](setup-aws.md) como comandos
prontos da CLI. Não virou script porque duas etapas dependem de valores que só existem depois
de passos manuais no console: o Skill ID e as credenciais de Alexa Skill Messaging.

### O que os scripts exigem

| Requisito | Detalhe |
|---|---|
| **Execution policy** | Os `.ps1` não são assinados. Use `-ExecutionPolicy Bypass` na chamada, como nos exemplos — evita alterar a política da máquina |
| **`python` no PATH** | Instale marcando "Add python.exe to PATH". Sem isso os dois scripts param logo no início |
| **`aws` no PATH** | Só para as verificações de nuvem e para o deploy. Sem ele, o `check` avisa e segue |
| **Elevação** | Não é necessária para verificar nem para o setup local. É para `install_task.ps1`, que registra a tarefa com `RunLevel Highest` |
| **PowerShell** | 5.1 serve. Os scripts evitam sintaxe exclusiva do 7 |

Conferir o PATH:

```powershell
(Get-Command python, aws -ErrorAction SilentlyContinue).Source
```

Se você acabou de instalar o Python, **abra um terminal novo** — o PATH não é reavaliado em
sessões já abertas, e é a causa mais comum de "instalei e continua dizendo que não achou".

## A configuração validada

Serve de referência quando algo diverge:

| | |
|---|---|
| Windows | 10 Pro 19045 |
| Python | 3.12 |
| Rede | Realtek PCIe GbE, cabeada, 1 Gbps |
| Fast Startup | desativado |
| Estados | S3 e Hibernar disponíveis |
| Echo | Echo Show 5, mesma sub-rede `/24` |
| Player | Spotify (Microsoft Store) |
| Idioma da skill | Português (BR) → `us-east-1` |
| Shell | PowerShell 7.6 e Windows PowerShell 5.1 |

Nada aqui é obrigatório além do que está na tabela de requisitos — é só o contexto em que os
testes rodaram.
