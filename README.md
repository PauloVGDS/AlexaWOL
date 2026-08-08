# AlexaWOL

Controle do PC pela Alexa — volume, ligar, desligar e suspender — sem mensalidade e sem
hardware adicional.

Skills prontas na loja cobram assinatura porque hospedam o servidor. Aqui o servidor é seu, e
o custo recorrente é **R$ 0**.

## Como funciona

O truque central é a interface oficial `Alexa.WakeOnLANController`: **a própria Echo transmite
o magic packet na rede local**. Não é preciso Raspberry Pi, ESP32, port-forward no roteador nem
emulação de lâmpada Hue/WeMo.

```
"Alexa, ligar o computador"
  └─ Alexa Cloud → Lambda (us-east-1)
       ├─ POST evento WakeUp → api.amazonalexa.com/v3/events
       │    └─ Echo transmite o magic packet na LAN → o PC liga
       └─ retorna Alexa.Response (powerState ON)
                                          ↑ nenhuma infraestrutura nossa nesse caminho

"Alexa, colocar o volume do computador em 30"
"Alexa, desligar o computador"
"Alexa, ativar suspensão do computador"
  └─ Alexa Cloud → Lambda → MQTT (HiveMQ, TLS+ACL) → agente Python no PC
                                                        └─ pycaw / shutdown / suspend
```

Ligar não depende de nada nosso. Volume e desligar só fazem sentido com o PC já ligado, então
o agente nunca precisa estar disponível 24 horas.

A documentação da Amazon descreve o "ligar" com um `Alexa.DeferredResponse` antes do evento
`WakeUp`. Isso é inviável no Lambda, que congela assim que retorna — não haveria como enviar o
evento "depois". Postar o evento durante a invocação e retornar a resposta normal funciona e é
bem mais simples.

## Requisitos

- PC com Windows e **rede cabeada** (Wake-on-LAN por Wi-Fi é pouco confiável)
- Um dispositivo Echo **na mesma sub-rede** do PC — requisito oficial da Amazon
- Python 3.11+ no PC (usa `tomllib` da biblioteca padrão)
- Conta AWS (o uso fica dentro do always-free do Lambda: 1M requisições/mês)
- Conta gratuita no HiveMQ Cloud Serverless
- Conta de desenvolvedor Alexa — **a mesma em que a Echo está registrada**

## Estrutura

| Caminho | O que é |
|---|---|
| `shared/protocol.py` | Assinatura HMAC dos comandos, compartilhada pelos dois lados |
| `agent/` | Serviço que roda no PC: escuta MQTT e executa volume/power |
| `lambda/` | Handler da Smart Home Skill v3 |
| `tools/wol_test.py` | Teste isolado de Wake-on-LAN, sem Alexa e sem nuvem |
| `tools/send_cmd.py` | Publica comandos assinados à mão, para testar o agente |
| `tests/test_lambda.py` | Exercita o handler sem AWS, sem broker e sem Alexa |
| `docs/setup-*.md` | Guias numerados de configuração do HiveMQ, da AWS e da skill |
| `docs/tocar-musica.md` | Como a cena de música funciona e como ligá-la a uma rotina |

## Ordem de instalação

Siga nesta ordem — cada etapa valida a anterior e evita depurar três camadas ao mesmo tempo.

1. **`docs/setup-wol.md`** — confirme que o PC acorda com um magic packet. Se falhar aqui,
   nada mais importa.
2. **`docs/setup-hivemq.md`** — crie o cluster e as duas credenciais separadas.
3. **`docs/setup-agent.md`** — instale o agente e teste volume/desligar por MQTT manual.
4. **`docs/setup-aws.md`** — publique o Lambda em `us-east-1`.
5. **`docs/setup-alexa.md`** — crie a skill e faça o account linking.

## Comandos de voz

| Frase | Interface | O que faz |
|---|---|---|
| "Alexa, ligar o computador" | `PowerController.TurnOn` | A Echo transmite o magic packet |
| "Alexa, desligar o computador" | `PowerController.TurnOff` | Desliga (S5), com janela de cancelamento |
| "Alexa, ativar suspensão do computador" | `SceneController.Activate` | Suspende (S3) |
| "Alexa, ativar música do computador" | `SceneController.Activate` | Abre a mídia configurada no agente |
| "Alexa, colocar o volume do computador em 30" | `Speaker.SetVolume` | Volume absoluto, 0–100 |
| "Alexa, aumentar o volume do computador em 20" | `Speaker.AdjustVolume` | Ajuste relativo |
| "Alexa, silenciar o computador" | `Speaker.SetMute` | Mudo |

Suspender e tocar música são endpoints separados, expostos como cenas, porque
`PowerController` só tem dois estados e o "desligar" já ocupa um deles. Para frases mais
curtas, crie Rotinas no app.

A Alexa **não** consegue mandar o áudio dela para o PC — a cena de música faz o próprio PC
abrir a mídia, e a Alexa serve só de gatilho. Detalhes em
[docs/tocar-musica.md](docs/tocar-musica.md).

## Desenvolvimento e testes

Os três testes rodam sem nuvem, sem broker e sem Alexa:

```powershell
# Handler do Lambda: discovery, cada diretiva e os erros
python tests\test_lambda.py

# Wake-on-LAN isolado — rode de OUTRO dispositivo da rede
python tools\wol_test.py 00-11-22-33-44-55

# Agente: publica comandos assinados à mão (exige config.toml)
python tools\send_cmd.py set_volume --percent 30
python tools\send_cmd.py set_volume --percent 30 --tamper   # deve ser recusado
python tools\send_cmd.py set_volume --percent 30 --stale    # deve ser recusado
```

Empacotar e publicar o Lambda:

```powershell
powershell -ExecutionPolicy Bypass -File lambda\build.ps1          # só empacota
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy  # empacota e sobe
```

## Segurança

Os comandos são assinados com HMAC-SHA256 sobre `{action, params, ts, nonce}`. O agente recusa
mensagem sem assinatura válida, com timestamp fora da janela de 30 segundos ou com nonce já
usado. As ações são uma allowlist fixa — o agente nunca executa string arbitrária vinda da rede.

Isso é defesa em profundidade: o HiveMQ já dá TLS, usuário/senha e ACL por tópico. A assinatura
protege contra um broker comprometido ou credencial vazada.
