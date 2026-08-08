# 3. Agente no PC

O serviço que escuta o broker e executa volume, desligar e suspender. Ele **não** participa do
"ligar" — quem transmite o magic packet é a Echo.

## Instalar

```powershell
cd C:\dev\AlexaWOL
python -m pip install -r agent\requirements.txt
Copy-Item agent\config.example.toml agent\config.toml
```

Edite `agent\config.toml` com o hostname do HiveMQ, as credenciais do usuário
**`alexawol-agent`** e o segredo HMAC. O arquivo está no `.gitignore`.

## Testar antes de instalar como serviço

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

**Sobre suspender:** com a hibernação habilitada, o Windows pode hibernar (S4) em vez de
suspender (S3). Na prática o Wake-on-LAN funciona nos dois estados desde que a placa esteja
armada. Se você quiser garantir o S3, rode `powercfg -h off` — ao custo de perder a hibernação.

Confira o que aconteceu de fato:

```powershell
Get-WinEvent -LogName System -MaxEvents 20 |
    Where-Object Id -in 1,42,107 |
    Select-Object TimeCreated, Id, Message
```

O evento 42 é a entrada em suspensão e o 107 é a saída.

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
