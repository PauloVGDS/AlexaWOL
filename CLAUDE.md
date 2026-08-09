# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

O código, os comentários e a documentação deste repositório são em português. Mantenha esse padrão.

## Comandos

```powershell
# Testes do handler do Lambda — não precisa de AWS, broker nem Alexa
python tests\test_lambda.py

# Teste isolado de Wake-on-LAN — rode de OUTRO dispositivo da rede
python tools\wol_test.py 00-11-22-33-44-55

# Exercitar o agente à mão (exige agent/config.toml preenchido e o agente rodando)
python tools\send_cmd.py set_volume --percent 30
python tools\send_cmd.py set_volume --percent 30 --tamper   # deve ser RECUSADO
python tools\send_cmd.py set_volume --percent 30 --stale    # deve ser RECUSADO

# Agente em primeiro plano, para ver o log
python agent\alexawol_agent.py

# Empacotar / publicar o Lambda (staging em %TEMP%, fora da arvore do projeto)
powershell -ExecutionPolicy Bypass -File lambda\build.ps1
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy

# Log do Lambda
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

**Ao mexer em `agent/` ou `shared/`, reinicie o agente** — ele executa o código que estava em
disco quando subiu, então editar o arquivo não muda nada até o reinício. É a falha silenciosa
mais comum aqui: o log do Lambda mostra tudo certo e o PC não reage.

```powershell
Stop-ScheduledTask -TaskName 'AlexaWOL Agent'; Start-ScheduledTask -TaskName 'AlexaWOL Agent'
```

O roteiro completo de extensão está em `docs/adicionar-funcionalidade.md`.

`tests/test_lambda.py` é um script standalone, não pytest. Ele imprime uma linha `OK`/`FALHOU`
por verificação e sai com código 1 se alguma falhar. Para rodar uma verificação isolada,
comente as demais — não há seleção por nome.

## Arquitetura

### Os dois caminhos são independentes

Esta é a coisa mais importante a entender antes de mexer em qualquer coisa:

- **Ligar** (`PowerController.TurnOn`) → o Lambda posta um evento `WakeUp` no Alexa event
  gateway e **a própria Echo transmite o magic packet na rede local**. Não passa pelo MQTT,
  não passa pelo agente, não passa por nenhuma infraestrutura nossa. Se "ligar" quebrar, o
  problema está em `alexa/events.py`, `alexa/auth.py`, no token do SSM ou no BIOS — nunca no
  agente.
- **Todo o resto** (volume, mudo, desligar, suspender) → Lambda publica no MQTT e o agente
  executa. Só faz sentido com o PC ligado, então o agente nunca precisa estar disponível 24 h.

Depurar um caminho olhando o outro é o erro mais fácil de cometer aqui.

### `shared/protocol.py` é copiado, não importado

O mesmo arquivo é usado pelos dois lados, mas eles são deployados separadamente:

- o agente o importa via `sys.path.insert` apontando para a raiz do repo;
- o `lambda/build.ps1` **copia** `shared/` para dentro do zip.

Se você mover ou renomear `shared/`, precisa ajustar os dois. Mudanças no formato da mensagem
ou na constante `MAX_AGE_SECONDS` quebram a compatibilidade entre Lambda e agente — os dois
precisam ser redeployados juntos.

### Restrições que parecem arbitrárias mas não são

**O Lambda tem que ficar em `us-east-1`.** pt-BR é servido por US East (N. Virginia); a Alexa
não entrega tráfego a um Lambda em outra região. O `~/.aws/config` da máquina aponta para
`sa-east-1`, então todo comando precisa de `--region us-east-1` explícito.

**O agente roda na sessão do usuário, não como SYSTEM.** O Core Audio do Windows é isolado na
sessão 0 — um serviço SYSTEM não consegue ler nem escrever o volume. Por isso
`agent/install_task.ps1` registra a tarefa com gatilho de logon e `LogonType Interactive`. Não
"corrija" isso para SYSTEM.

**COM precisa ser inicializado por thread.** `volume.com_init()` é chamado tanto na thread do
`loop_forever` do paho quanto na thread de refresh de estado. Qualquer thread nova que toque
`actions/volume.py` precisa chamá-lo antes.

**`pycaw>=20251023`.** A API mudou: `AudioUtilities.GetSpeakers()` devolve um `AudioDevice`
com a propriedade `EndpointVolume`. O padrão antigo `speakers.Activate(IAudioEndpointVolume...)`
que aparece em quase todo tutorial na internet **não funciona mais**.

**`LWA_CLIENT_ID`/`LWA_CLIENT_SECRET` são os de "Alexa Skill Messaging".** Não são os do
Security Profile usado no account linking, apesar do nome da variável sugerir isso. Ficam em
Build → Permissions no console da skill, atrás do botão SHOW, e só existem depois de ligar o
toggle **Send Alexa Events** — que também é o que faz a Alexa enviar o `AcceptGrant`. Os dois
pares têm formato idêntico, então a troca não produz erro em lugar nenhum: a falha aparece só
no `TurnOn`, o único caminho que usa esses valores. Se alguém "corrigir" isso para as
credenciais do account linking, o "ligar" para de funcionar sem nenhum sintoma em outro lugar.

**Nada de `DeferredResponse`.** A doc da Amazon descreve o "ligar" como DeferredResponse →
evento `WakeUp` → resposta final. Isso é inviável: o Lambda congela ao retornar, então não há
como enviar o evento "depois". O que funciona é postar o evento durante a invocação e retornar
a `Alexa.Response` normal. Já foi testado; não reintroduza o DeferredResponse.

### Decisões deliberadas no Lambda

**`EndpointHealth` sempre reporta `OK`**, mesmo com o PC desligado (`alexa/state.py`). Se
reportasse `UNREACHABLE`, a Alexa trataria o dispositivo como fora do ar e poderia recusar
justamente o "ligar o computador" — o comando que precisa funcionar nesse estado. Quem carrega
a informação de ligado/desligado é o `powerState`.

**Fire-and-forget.** `bridge/mqtt_client.publish_command()` publica e retorna; nunca espere o
agente confirmar execução. A Alexa corta em 8 s e o Lambda congela ao retornar. As respostas de
volume em `alexa/speaker.py` são otimistas — devolvem o valor pedido, e o agente republica o
estado real logo em seguida, então um desencontro se corrige sozinho no próximo `ReportState`.

**Estado por mensagem retida + last will.** O agente publica `{online, volume, muted}` retained
em `alexawol/state` e configura um LWT com `online: false`. É assim que a Alexa sabe se o PC
está ligado sem ninguém fazer polling. Ausência de retained significa "agente nunca conectou"
→ PC desligado.

**Cenas para o que não cabe em ligar/desligar.** `PowerController` só tem dois estados e o
"desligar" já ocupa um deles, então cada ação extra vira um endpoint `SceneController` próprio
— hoje "Suspensão do computador" e "Música do computador".

Acrescentar uma cena exige **quatro** mudanças coordenadas, e esquecer qualquer uma produz
falha silenciosa:

1. a ação na allowlist de `shared/protocol.py`;
2. o ramo no `dispatch()` do agente;
3. o endpoint em `discovery.py`;
4. **a entrada em `_ACTION_BY_ENDPOINT` de `alexa/scene.py`.**

O item 4 é o mais fácil de esquecer e o mais perigoso. Antes de existir a segunda cena, o
`scene.py` publicava `suspend` incondicionalmente e passava nos testes — quando a cena de
música entrou, ativá-la teria suspendido o PC. `tests/test_lambda.py` agora cobre isso
verificando que cada cena publica a **sua** ação, e que endpoint desconhecido devolve
`NO_SUCH_ENDPOINT` em vez de cair num padrão.

**O controle de mídia usa o SMTC, com teclas de mídia só como plano B.** O
`GlobalSystemMediaTransportControlsSessionManager` é o que permite `Play` e `Pause` corretos —
o Windows tem uma tecla única que **alterna**, então mapear as duas operações da Alexa nela
faria "pausar" retomar a música já pausada. Por isso `play()` e `pause()` são SMTC-only e
levantam erro sem sessão ativa, em vez de cair na tecla e fazer o oposto do pedido.

O SMTC também dá a posição de reprodução, que é o que faz `Previous` acertar: passados 3 s um
único comando só rebobina, e o agente manda dois. `StartOver` é ação separada de `Previous`
justamente porque são intenções diferentes — unificar quebraria uma delas.

As chamadas `try_*_async` **devolvem um booleano**. Ignorá-lo faz uma recusa do player passar
por sucesso e o plano B nunca ser tentado; `_executar_smtc` propaga esse retorno de propósito.

**Nenhuma métrica declara `unitOfMeasure`, e isso é deliberado.** O único asset aplicável seria
`Alexa.Unit.Percent`, que o app da Alexa renderiza como a palavra "Por cento" em pt-BR, e não
existe asset para gigabytes. A unidade vai no nome ("Memória usada em gigabytes"). Os nomes são
também alvos de voz, então nada de "%" ou "(GB)" — precisam ser pronunciáveis.

**`alexa/metrics.py` é fonte única de verdade.** O `discovery.py` monta as capabilities e o
`state.py` monta as propriedades a partir da mesma tupla. Definir nos dois lugares repetiria o
erro que o `scene.py` cometeu, em que uma lista e um mapa saíram de sincronia. Métrica nova é
uma entrada ali mais o campo correspondente no estado publicado pelo agente.

**A leitura da GPU responde por ~96% do custo do agente.** Medido: numa janela de 150 s o
processo consome 0,09 s de CPU e os PowerShell da GPU consomem 2,73 s. É `subprocess` porque o
contador `\GPU Engine(*)\Utilization Percentage` serve para qualquer fabricante — nvidia-smi
cobriria só NVIDIA.

Daí três decisões que não devem ser desfeitas: a chamada só acontece na thread periódica, nunca
no caminho dos comandos; `atualizar_gpu()` limita a frequência internamente a 120 s, e não no
chamador, para ninguém tornar a leitura cara por engano; e `metricas()` apenas lê o cache. Baixar
o intervalo para os 30 s do ciclo de estado dobraria com folga o consumo do agente inteiro.

`tools/medir_agente.py` refaz a medição — ele separa o processo dos subprocessos, que é o que
revela onde o custo realmente está.

**A mídia da cena de música nunca trafega pela rede.** O comando é só o verbo `play_music`; o
alvo vem de `[media].target` no `config.toml` do agente. Não mova isso para o payload — quem
tivesse o segredo HMAC faria o PC abrir qualquer programa.

### Segurança

Todo comando carrega HMAC-SHA256 sobre `{action, params, ts, nonce}`. O agente recusa
assinatura inválida, timestamp fora de ±30 s e nonce repetido, e só executa ações da allowlist
em `shared/protocol.ACTIONS`. Ao adicionar uma ação nova, inclua-a nessa allowlist **e** no
`dispatch()` do agente — só um dos dois não basta.

O `HMAC_SECRET` do Lambda e o `secret` do `agent/config.toml` precisam ser idênticos. As
credenciais MQTT são duas e diferentes: `alexawol-lambda` (publica em `cmd`, assina `state`) e
`alexawol-agent` (assina `cmd`, publica `state`).

### Credenciais: centralizadas em um arquivo, nunca no repositório

**Decisão:** todos os segredos do lado do PC ficam num único arquivo, em
`%LOCALAPPDATA%\AlexaWOL\config.toml` — credencial do agente, credencial do publisher, segredo
HMAC e o alvo de mídia. Não são espalhados por variáveis de ambiente, arquivos `.env` separados
ou cofre externo. Note que o local é **fora** do repositório; o motivo está no último item das
consequências.

O motivo é operacional: um arquivo só significa um lugar para editar ao rotacionar uma senha,
um lugar para conferir quando algo para de autenticar, e uma única entrada no `.gitignore`
para proteger. Segredo espalhado é segredo que vaza pela cópia esquecida.

**Consequências que precisam ser respeitadas:**

- `agent/config.toml` **nunca** é commitado. Já está no `.gitignore`; ao mexer nesse arquivo,
  confirme com `git status` que ele não aparece. Versionado é `config.example.toml`, e nele
  todo valor sensível fica como `""` ou `TROQUE-ME`.
- **Nunca imprima o conteúdo desses campos** em resposta, log ou mensagem de commit. Para
  validar a configuração, verifique presença, tamanho e formato — não o valor. Comparar duas
  senhas se faz por hash, não exibindo as duas.
- O `[publisher]` concentra a credencial do Lambda no PC, além da do agente. É consciente: sem
  ela, `tools/send_cmd.py` não consegue publicar em `alexawol/cmd` e a alternativa seria
  afrouxar a ACL do agente permanentemente — o que quebraria a separação entre quem emite
  comandos e quem os executa. Um arquivo protegido é melhor do que uma ACL errada.
- Como consequência do ponto acima, quem obtém o `config.toml` obtém tudo: as duas credenciais
  MQTT e o segredo HMAC. É o modelo de ameaça aceito — a proteção é o arquivo não sair da
  máquina, não a compartimentação interna dele.
- **E é por isso que ele não mora na árvore do projeto.** O local é
  `%LOCALAPPDATA%\AlexaWOL\config.toml`, resolvido por `agent/config_location.py`. O
  `.gitignore` protege o repositório git e **não protege contra sincronização**: com o projeto
  dentro de OneDrive, Dropbox ou Google Drive, um `config.toml` ali seria enviado à nuvem do
  serviço e a todo dispositivo da conta — exatamente o "sair da máquina" que o modelo proíbe.
  Isso não é hipotético: na instalação original o repositório vivia dentro do OneDrive e o
  arquivo esteve sincronizado até ser movido. O agente e o `send_cmd.py` avisam alto se o config que
  carregarem estiver numa pasta sincronizada.
- O lado do Lambda espelha isso em variáveis de ambiente da função, criptografadas em repouso.
  A única exceção é o refresh token do account linking, que fica no SSM Parameter Store como
  SecureString por ser escrito em tempo de execução, quando chega o `AcceptGrant`.

## Ambiente alvo

Os docs e os testes usam valores de exemplo. **Troque pelos seus** — os identificadores reais
não vão para o repositório, e o `agent/config.toml` mora fora da árvore do projeto.

| Item | Exemplo nos docs | Onde está o seu |
|---|---|---|
| MAC do PC (alvo do WOL) | `00-11-22-33-44-55` | variável `PC_MAC` do Lambda |
| PC | `192.168.1.10/24`, interface cabeada | `ipconfig` |
| Echo | `192.168.1.11` — mesma sub-rede, requisito oficial | app Alexa → dispositivo → sobre |
| Conta AWS | `123456789012`, região obrigatória `us-east-1` | `aws sts get-caller-identity` |
| Skill ID | `amzn1.ask.skill.a1b2c3d4-…` | console da skill, "View Skill ID" |

Para descobrir o MAC e a interface no Windows:

```powershell
Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object Name, MacAddress, LinkSpeed
```

## Estado atual

Código e testes completos. Falta a configuração externa, que exige login interativo: cluster
HiveMQ, perfil Login with Amazon, criação da skill e o deploy do Lambda. Os guias em `docs/`
estão numerados na ordem em que cada etapa valida a anterior — comece sempre por
`docs/setup-wol.md`, porque se o PC não acorda com um magic packet, nada mais importa.
