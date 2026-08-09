# AlexaWOL

Controle do PC pela Alexa — ligar, desligar, suspender, volume e mídia — sem mensalidade e sem
hardware adicional.

Skills prontas na loja cobram assinatura porque hospedam o servidor. Aqui o servidor é seu, e o
custo recorrente é **R$ 0**: o uso cabe folgadamente no always-free do AWS Lambda e no plano
gratuito permanente do HiveMQ.

## Arquitetura

O projeto tem **dois caminhos de comando independentes**. Entender essa separação é o que torna
qualquer defeito diagnosticável, porque ela diz de antemão onde o problema *não* pode estar.

```
"Alexa, ligar o computador"
  └─ Alexa Cloud → Lambda (us-east-1)
       ├─ POST evento WakeUp → api.amazonalexa.com/v3/events
       │    └─ a Echo transmite o magic packet na LAN → o PC liga
       └─ retorna Alexa.Response (powerState ON)
                                    ↑ nenhuma infraestrutura nossa nesse caminho

"Alexa, colocar o volume do computador em 30"
"Alexa, desligar / suspender / próxima no computador"
  └─ Alexa Cloud → Lambda → MQTT (HiveMQ, TLS + ACL) → agente Python no PC
                                                          └─ pycaw / shutdown / teclas de mídia
```

**Ligar** usa a interface oficial `Alexa.WakeOnLANController`: o Lambda posta um evento e **a
própria Echo transmite o magic packet** na rede local. Não passa pelo MQTT, não passa pelo
agente, não passa por servidor nenhum nosso. Foi essa descoberta que eliminou a necessidade de
um Raspberry Pi, ESP32 ou port-forward no roteador.

**Todo o resto** só faz sentido com o PC ligado, então trafega por MQTT até um agente local. O
agente nunca precisa estar disponível 24 horas.

Na prática isso significa: se "ligar" falhar, o problema está no evento, no token ou no BIOS —
nunca no agente. Se o resto falhar, está no broker ou no agente — nunca no event gateway.

### As três peças

| Peça | O que faz | Onde roda |
|---|---|---|
| `lambda/` | Traduz diretivas da Alexa em ações; fala com o event gateway e com o broker | AWS, `us-east-1` |
| `agent/` | Escuta o broker e executa no Windows: volume, energia, mídia | Sessão do usuário, no PC |
| `shared/protocol.py` | Assinatura HMAC e allowlist de ações — usado pelos dois lados | Ambos |

O `shared/` é **copiado** para dentro do zip do Lambda pelo `build.ps1`, não importado. Mudar o
formato da mensagem exige redeployar os dois lados juntos.

### Segurança em duas camadas

O HiveMQ dá TLS, usuário/senha e ACL por tópico, com **credenciais separadas** para quem publica
comandos e quem os executa. Acima disso, todo comando carrega HMAC-SHA256 sobre
`{action, params, ts, nonce}` — o agente recusa assinatura inválida, timestamp fora de 30 s e
nonce repetido, e só executa ações de uma allowlist fixa.

A segunda camada existe para o caso de broker comprometido ou credencial vazada. E é por isso
que o alvo da mídia mora no config local, nunca no payload: o comando diz "toque", não *o quê*.

### Estado sem polling

O agente publica `{online, volume, muted}` como mensagem **retida** e configura um *last will*
com `online: false`. É assim que a Alexa sabe se o PC está ligado sem ninguém ficar consultando.
Ausência de retained significa "o agente nunca conectou" — ou seja, PC desligado.

## Requisitos

- Windows 10/11 com **rede cabeada** (Wake-on-LAN por Wi-Fi é pouco confiável)
- **BIOS com `Power On by PCI-E` ativo e `ErP Ready` desativado** — não é sugestão: a
  configuração de fábrica da maioria das placas corta a energia da rede no desligamento, e aí
  nenhum ajuste do Windows faz o "ligar" funcionar
- **Python 3.11+** no PC (o agente usa `tomllib`)
- Um dispositivo Echo **na mesma sub-rede** do PC — requisito oficial da Amazon
- Conta AWS, conta gratuita no HiveMQ, e conta de desenvolvedor Alexa **a mesma da Echo**

**Rode todos os `.ps1` num PowerShell aberto como Administrador.** Botão direito no menu
Iniciar → Terminal (Administrador). Antes de qualquer coisa, o verificador diz o que falta:

```powershell
powershell -ExecutionPolicy Bypass -File tools\check_requisitos.ps1
```

Ele só lê o sistema. O que ele **não** consegue checar — BIOS, roteador e consoles web — está
listado em [docs/requisitos-e-variacoes.md](docs/requisitos-e-variacoes.md), junto do que costuma
diferir entre máquinas.

## Instalação

Reserve algo entre uma e duas horas. A maior parte é preencher formulário em console web; o
código já está pronto.

**Parte local — linear, cada etapa valida a anterior.**

| # | Guia | O que resolve |
|---|---|---|
| 1 | [setup-wol.md](docs/setup-wol.md) | **BIOS** e confirmar que o PC acorda — sem Alexa, sem nuvem |
| 2 | [setup-hivemq.md](docs/setup-hivemq.md) | Cluster MQTT e as duas credenciais separadas |
| 3 | [setup-agent.md](docs/setup-agent.md) | Agente no PC, testado por comando manual |

Não pule a primeira: se o PC não acorda com um magic packet, nada mais importa. E o BIOS é
requisito, não sugestão — a configuração de fábrica da maioria das placas impede o WOL a partir
do desligamento.

O passo 3 é quase todo automatizável, num terminal **como Administrador**:

```powershell
powershell -ExecutionPolicy Bypass -File tools\setup_local.ps1   # dependências, config, segredo
# preencha as credenciais do HiveMQ no config.toml que ele criou
powershell -ExecutionPolicy Bypass -File agent\install_task.ps1  # registra o serviço
```

**Parte na nuvem — não é linear.** A AWS precisa do Skill ID e a skill precisa do ARN do
Lambda, então [setup-aws.md](docs/setup-aws.md) e [setup-alexa.md](docs/setup-alexa.md) se
entrelaçam. Comece pelo [setup-aws.md](docs/setup-aws.md), que abre com a sequência de oito
passos que minimiza as idas e vindas entre os dois consoles.

O que exige navegador — HiveMQ, Login with Amazon e a skill — não tem como automatizar.

## Ordem de leitura

Depende do que você quer:

**Vou instalar** → siga a tabela acima na ordem. Volte a
[requisitos-e-variacoes.md](docs/requisitos-e-variacoes.md) se algo divergir da sua máquina.

**Quero entender antes de instalar** → a seção de arquitetura acima, depois
[CLAUDE.md](CLAUDE.md), que reúne as decisões de projeto e as restrições que parecem arbitrárias
mas não são.

**Travei em alguma coisa** → [problemas-encontrados.md](docs/problemas-encontrados.md), que é
indexado por sintoma. Todo problema listado ali aconteceu de verdade durante a construção.

**Quero estender** → [adicionar-funcionalidade.md](docs/adicionar-funcionalidade.md) traz o
roteiro completo, incluindo os três pontos de implantação que falham em silêncio quando
esquecidos.

**Quero tocar mídia** → [tocar-musica.md](docs/tocar-musica.md) explica por que a Alexa não
consegue mandar o áudio dela para o PC, e como fazer o PC tocar sozinho.

## Comandos de voz

| Frase | Interface | O que faz |
|---|---|---|
| "Alexa, ligar o computador" | `PowerController.TurnOn` | A Echo transmite o magic packet |
| "Alexa, desligar o computador" | `PowerController.TurnOff` | Desliga (S5), com janela de cancelamento |
| "Alexa, ativar suspensão do computador" | `SceneController.Activate` | Suspende (S3) |
| "Alexa, ativar música do computador" | `SceneController.Activate` | Abre a mídia configurada |
| "Alexa, colocar o volume do computador em 30" | `Speaker.SetVolume` | Volume absoluto, 0–100 |
| "Alexa, aumentar o volume do computador em 20" | `Speaker.AdjustVolume` | Ajuste relativo |
| "Alexa, silenciar o computador" | `Speaker.SetMute` | Mudo |
| "Alexa, continuar no computador" | `PlaybackController.Play` | Retoma a reprodução |
| "Alexa, pausar no computador" | `PlaybackController.Pause` | Pausa |
| "Alexa, próxima no computador" | `PlaybackController.Next` | Avança a faixa |
| "Alexa, anterior no computador" | `PlaybackController.Previous` | Volta uma faixa |
| "Alexa, recomeçar no computador" | `PlaybackController.StartOver` | Recomeça a faixa atual |

O controle de reprodução usa o **SMTC**, a API de sessão de mídia do Windows — a mesma do
overlay que aparece ao apertar as teclas de volume. **Não é específico do Spotify**: vale para
navegador tocando YouTube, VLC, Groove e qualquer app que apareça naquele overlay.

Suspender e tocar música são endpoints separados, expostos como cenas, porque `PowerController`
só tem dois estados e o "desligar" já ocupa um deles. Para frases mais curtas, crie Rotinas no
app.

## Informações no app

Além do interruptor, o card do computador mostra métricas em leitura apenas — e dá para
perguntá-las por voz, tipo *"Alexa, qual é o uso do processador do computador?"*:

| Métrica | Fonte |
|---|---|
| Tempo ligado em minutos | `psutil.boot_time()` |
| Uso do processador | psutil |
| Uso da placa de vídeo | contador de desempenho do Windows — **qualquer fabricante** |
| Memória usada / total em gigabytes | psutil |
| Disco usado / total em gigabytes | psutil |

São instâncias de `Alexa.RangeController` com `nonControllable: true`, o que faz o app exibir o
valor sem oferecer controle. Com o PC desligado nenhuma métrica é reportada — mostrar zero
seria mentira.

**A unidade vai no nome, não em `unitOfMeasure`.** O catálogo da Amazon só tem
`Alexa.Unit.Percent`, que o app renderiza como a palavra "Por cento", e não existe asset para
gigabytes. Pôr a unidade no próprio nome resolve os dois casos e ainda funciona por voz.

Os nomes também são alvos de voz, então evitam caracteres não pronunciáveis — é por isso que
está "em gigabytes" e não "(GB)", e por isso o "%" não aparece como símbolo.

**Temperatura ficou de fora de propósito.** O Windows não a expõe de forma confiável: o WMI
responde "operação não suportada" na maioria dos desktops e placas AMD não têm equivalente ao
`nvidia-smi`. A única fonte seria o LibreHardwareMonitor rodando em segundo plano, e exigir um
aplicativo extra permanente não compensa por um número.

### Quanto o agente custa

Medido nesta máquina, numa janela de 150 s com `tools\medir_agente.py`:

```
CPU do processo      0,09 s      ← o agente em si
CPU dos subprocessos 2,73 s      ← leitura da GPU
ocupação de 1 núcleo 1,88%
do processador todo  0,157%
memória (pico)       37 MB
```

O agente propriamente dito é gratuito: passa o tempo bloqueado esperando rede. **Quase todo o
custo é a leitura da GPU**, que dispara um PowerShell e leva ~2,5 s. Por isso ela é relida a
cada 2 minutos, e não a cada ciclo de estado — a 30 s a ocupação era 4,78% de um núcleo.

Se você quiser custo praticamente zero, remova a entrada `PC.GPU` de `lambda/alexa/metrics.py`
e a leitura correspondente no agente: sobra 0,06% de um núcleo.

## Estrutura

| Caminho | O que é |
|---|---|
| `lambda/` | Handler da Smart Home Skill v3, um módulo por interface |
| `agent/` | Serviço do PC: MQTT, volume (`pycaw`), energia e mídia |
| `shared/protocol.py` | Assinatura HMAC e allowlist, compartilhados |
| `tools/check_requisitos.ps1` | Diagnóstico do sistema — só lê, não altera |
| `tools/setup_local.ps1` | Instala dependências, cria o config e gera o segredo |
| `tools/wol_test.py` | Teste isolado de Wake-on-LAN, sem Alexa e sem nuvem |
| `tools/medir_agente.py` | Mede CPU e memória do agente, separando os subprocessos |
| `tools/send_cmd.py` | Publica comandos assinados à mão, para testar o agente |
| `tests/test_lambda.py` | Exercita o handler sem AWS, sem broker e sem Alexa |
| `docs/` | Guias de instalação, diagnóstico e extensão |

## Desenvolvimento e testes

Os três testes rodam sem nuvem, sem broker e sem Alexa:

```powershell
python tests\test_lambda.py                                  # handler do Lambda
python tools\wol_test.py 00-11-22-33-44-55                   # WOL — rode de OUTRO dispositivo
python tools\send_cmd.py set_volume --percent 30             # agente, por comando manual
python tools\send_cmd.py set_volume --percent 30 --tamper    # deve ser recusado
python tools\send_cmd.py set_volume --percent 30 --stale     # deve ser recusado
```

Publicar o Lambda:

```powershell
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy
```

⚠️ Ao mexer em `agent/` ou `shared/`, **reinicie o agente** — ele executa o código que estava em
disco quando subiu:

```powershell
Stop-ScheduledTask -TaskName 'AlexaWOL Agent'; Start-ScheduledTask -TaskName 'AlexaWOL Agent'
```
