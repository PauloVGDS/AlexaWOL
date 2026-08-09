# 3. Agente no PC

O serviço que escuta o broker e executa volume, desligar e suspender. Ele **não** participa do
"ligar" — quem transmite o magic packet é a Echo.

## Instalar

**Abra o PowerShell como Administrador** — botão direito no menu Iniciar → Terminal
(Administrador). O registro da tarefa agendada exige elevação, e usar o mesmo terminal do
começo ao fim evita que um passo falhe por privilégio e o seguinte parta de um estado
incompleto.

```powershell
cd C:\dev\AlexaWOL
python -m pip install -r agent\requirements.txt

# O config NÃO fica na árvore do projeto — veja o porquê logo abaixo
New-Item -ItemType Directory -Force "$env:LOCALAPPDATA\AlexaWOL" | Out-Null
Copy-Item agent\config.example.toml "$env:LOCALAPPDATA\AlexaWOL\config.toml"
```

Edite `%LOCALAPPDATA%\AlexaWOL\config.toml` com o hostname do HiveMQ, as credenciais do
usuário **`alexawol-agent`** e o segredo HMAC.

### Por que fora do projeto

O `.gitignore` impede que esse arquivo vá para o repositório, mas **não impede que ele saia da
máquina**. Se você clonar este projeto dentro de uma pasta do OneDrive, Dropbox ou Google Drive
— comum, já que `Documentos` costuma ser sincronizado — tudo ali é enviado para a nuvem do
serviço e para todos os dispositivos logados na conta. Um `config.toml` em `agent\` levaria
junto as duas credenciais MQTT e o segredo HMAC, ou seja, controle total da máquina, fora dela.

Aconteceu na instalação original deste projeto: o repositório vivia dentro do OneDrive e o
arquivo esteve sincronizado até ser movido.

`%LOCALAPPDATA%` não é sincronizado por OneDrive, Dropbox nem Google Drive. O agente procura o
config nesta ordem: argumento de linha de comando, variável `ALEXAWOL_CONFIG`,
`%LOCALAPPDATA%\AlexaWOL\config.toml` e, por último, `agent\config.toml`. Se o que ele carregar
estiver numa pasta sincronizada, ele avisa no log — o mesmo vale para o `send_cmd.py`.

A seção `[media]` é opcional — só é usada pela cena "Música do computador". Se você não for
usá-la, deixe `target = ""`; o comando simplesmente falha com mensagem clara no log, sem
derrubar o agente. Ver [tocar-musica.md](tocar-musica.md).

## Testar antes de instalar como serviço

Antes: preencha `[publisher]` no `config.toml` com a credencial do **Lambda**
(`alexawol-lambda`). O `send_cmd.py` faz o papel do Lambda e precisa publicar em
`alexawol/cmd`, o que a credencial do agente não pode — ver
[setup-hivemq.md](setup-hivemq.md).

Rode em primeiro plano, num terminal:

```powershell
python agent\alexawol_agent.py
```

Você deve ver `conectado ao broker; assinando alexawol/cmd`. Deixe rodando e, em **outro**
terminal, mande comandos:

```powershell
python tools\send_cmd.py set_volume --percent 30
python tools\send_cmd.py adjust_volume --delta 10
python tools\send_cmd.py set_mute --muted true
python tools\send_cmd.py set_mute --muted false
python tools\send_cmd.py report
python tools\send_cmd.py play_music   # só se você preencheu [media].target
```

Confira que o volume do Windows realmente mudou a cada comando.

### Os testes negativos

Estes **devem** ser recusados. Se algum passar, pare e investigue antes de expor o Lambda:

```powershell
python tools\send_cmd.py set_volume --percent 30 --tamper   # assinatura inválida
python tools\send_cmd.py set_volume --percent 30 --stale    # timestamp de 1h atrás
```

No log do agente devem aparecer `comando recusado: assinatura inválida` e
`comando recusado: timestamp fora da janela`.

### Energia

Deixe por último, porque derrubam a sessão:

```powershell
python tools\send_cmd.py shutdown --delay 30
python tools\send_cmd.py abort        # cancela — teste este primeiro!
python tools\send_cmd.py suspend
```

**Sobre suspender:** circula a ressalva de que, com a hibernação habilitada, o Windows
hibernaria (S4) em vez de suspender (S3). **Medido nesta máquina: não acontece.** O suspender
entrou em S3 de verdade com a hibernação ativa, então **não** é preciso `powercfg -h off` e
você continua com a hibernação disponível.

O comportamento depende de firmware e drivers, então vale remedir ao trocar de máquina. De
todo modo o WOL funciona nos dois estados desde que a placa esteja armada.

Confira o que aconteceu de fato:

```powershell
Get-WinEvent -LogName System -MaxEvents 20 |
    Where-Object Id -in 1,42,107 |
    Select-Object TimeCreated, Id, Message
```

O evento 42 é a entrada em suspensão e o 107 é a saída.

## Sobre manter o `[publisher]` preenchido

Ele concentra as duas credenciais MQTT no mesmo arquivo, junto do segredo HMAC. É consciente:
sem ele o `send_cmd.py` não publica, e a alternativa seria afrouxar a ACL do agente de forma
permanente — o que quebraria a separação entre quem emite comandos e quem os executa. Um
arquivo protegido é melhor que uma ACL errada.

O que sustenta essa escolha é o arquivo **não sair da máquina**, e é exatamente por isso que a
seção acima insiste no `%LOCALAPPDATA%`. Dentro do OneDrive, a premissa se quebra e a decisão
deixa de ser defensável.

## Instalar como Tarefa Agendada

```powershell
powershell -ExecutionPolicy Bypass -File agent\install_task.ps1
Start-ScheduledTask -TaskName 'AlexaWOL Agent'
```

A tarefa roda **na sua sessão, no logon** — e não como SYSTEM. Isso é deliberado: o Core Audio
do Windows é isolado na sessão 0, então um serviço SYSTEM não conseguiria mexer no volume.
Não é limitação prática, porque ao acordar do S3 a sessão continua viva mesmo bloqueada, e o
"ligar" nunca depende do agente.

Para acompanhar:

```powershell
Get-ScheduledTask -TaskName 'AlexaWOL Agent' | Get-ScheduledTaskInfo
```

Para remover: `powershell -ExecutionPolicy Bypass -File agent\install_task.ps1 -Uninstall`

## Próximo passo

[setup-aws.md](setup-aws.md)
