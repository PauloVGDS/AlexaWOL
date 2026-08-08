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

# Empacotar / publicar o Lambda
powershell -ExecutionPolicy Bypass -File lambda\build.ps1
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy

# Log do Lambda
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

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

**Dois endpoints no Discovery.** `PowerController` só tem ligar/desligar, e o usuário quer
suspender e desligar separados. Por isso existe um segundo endpoint exposto como
`SceneController` ("Suspensão do computador"). Adicionar uma terceira ação de energia significa
mais um endpoint-cena.

### Segurança

Todo comando carrega HMAC-SHA256 sobre `{action, params, ts, nonce}`. O agente recusa
assinatura inválida, timestamp fora de ±30 s e nonce repetido, e só executa ações da allowlist
em `shared/protocol.ACTIONS`. Ao adicionar uma ação nova, inclua-a nessa allowlist **e** no
`dispatch()` do agente — só um dos dois não basta.

O `HMAC_SECRET` do Lambda e o `secret` do `agent/config.toml` precisam ser idênticos. As
credenciais MQTT são duas e diferentes: `alexawol-lambda` (publica em `cmd`, assina `state`) e
`alexawol-agent` (assina `cmd`, publica `state`).

## Ambiente alvo

Valores concretos desta instalação, referenciados pelos docs e pelos testes:

| Item | Valor |
|---|---|
| MAC do PC (alvo do WOL) | `00-11-22-33-44-55` |
| PC | `192.168.1.10/24`, `Ethernet 3` (Realtek, cabeada) |
| Echo Show | `192.168.1.11` — mesma sub-rede, requisito oficial |
| Conta AWS | `123456789012`, região obrigatória `us-east-1` |

## Estado atual

Código e testes completos. Falta a configuração externa, que exige login interativo: cluster
HiveMQ, perfil Login with Amazon, criação da skill e o deploy do Lambda. Os guias em `docs/`
estão numerados na ordem em que cada etapa valida a anterior — comece sempre por
`docs/setup-wol.md`, porque se o PC não acorda com um magic packet, nada mais importa.
