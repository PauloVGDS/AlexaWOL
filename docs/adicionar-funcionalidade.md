# Adicionar uma funcionalidade nova

Roteiro para quem já tem o projeto instalado e funcionando. Cobre desde escolher a interface
certa da Alexa até os três passos de implantação que, esquecidos, produzem falhas silenciosas.

## O que precisa ser reimplantado — e por que cada um falha calado

Esta é a parte que mais custa tempo. Uma funcionalidade nova toca **três lugares
independentes**, e cada um tem seu próprio jeito de parecer que está atualizado sem estar:

| Camada | Como atualizar | Se esquecer |
|---|---|---|
| **Lambda** | `build.ps1 -Deploy` | A Alexa manda a diretiva e o handler não sabe roteá-la |
| **Agente** | **reiniciar a tarefa agendada** | Ele roda o código que estava em disco **quando subiu** — editar o arquivo não muda nada |
| **Alexa** | "Alexa, descobrir dispositivos" | Ela usa as capacidades memorizadas na última descoberta e nem tenta enviar a diretiva nova |

O caso do agente é o mais traiçoeiro, porque tudo o mais parece certo. O log do Lambda mostra
a diretiva chegando e o `publicado: <ação>` saindo — mas o agente, com a cópia velha de
`shared/protocol.py` em memória, recusa a ação por não estar na allowlist. **Aconteceu ao
implementar o "avançar faixa"**: a nuvem inteira funcionava e nada acontecia no PC.

Para conferir se o agente está com o código atual:

```powershell
Get-Process pythonw | Select-Object Id, StartTime
Get-Item agent\actions\*.py, shared\protocol.py | Select-Object Name, LastWriteTime
```

Se algum arquivo é mais novo que o `StartTime`, reinicie:

```powershell
Stop-ScheduledTask -TaskName 'AlexaWOL Agent'
Start-ScheduledTask -TaskName 'AlexaWOL Agent'
```

(Não existe `Restart-ScheduledTask`.)

## Escolher a interface da Alexa

Metade do trabalho é decidir isso. A interface certa dá frase natural de graça; a errada
obriga a inventar contorno.

| O que você quer | Interface | Frase resultante |
|---|---|---|
| Um estado ligado/desligado | `Alexa.PowerController` | "ligar/desligar o computador" |
| Volume ou mudo | `Alexa.Speaker` | "colocar o volume do computador em 30" |
| Avançar, voltar, pausar mídia | `Alexa.PlaybackController` | "próxima no computador" |
| Uma ação sem estado — dispara e pronto | `Alexa.SceneController` | "ativar \<nome da cena\>" |

Duas regras que economizam retrabalho:

**`PowerController` só tem dois estados.** "Desligar" já ocupa um deles, então suspender,
hibernar ou qualquer terceira ação de energia precisa de uma cena própria.

**Nomes de cena colidem com intents nativos.** Evite *música*, *som*, *tocar*, *playlist* e
*rádio* — a Alexa captura a frase antes de chegar na skill. Detalhes em
[tocar-musica.md](tocar-musica.md).

## Checklist por tipo de mudança

### A. Ação nova no PC (sem interface nova)

Exemplo: bloquear a tela, tirar print.

1. `shared/protocol.py` — acrescentar a ação em `ACTIONS`
2. `agent/actions/` — implementar (módulo novo ou função num existente)
3. `agent/alexawol_agent.py` — ramo no `dispatch()`
4. `tools/send_cmd.py` — acrescentar às `choices` do argparse

⚠️ **Os itens 1 e 3 andam juntos.** Só a allowlist faz o comando ser recusado; só o dispatch
faz estourar `ValueError`. Nenhum dos dois erros é óbvio de fora.

Já dá para testar sem tocar na Alexa:

```powershell
python tools\send_cmd.py <acao>
```

### B. Cena nova

Além dos passos de (A), **quatro** mudanças coordenadas:

1. `lambda/config.py` — `*_ENDPOINT_ID` e `*_FRIENDLY_NAME`
2. `lambda/alexa/discovery.py` — mais um `_scene_endpoint(...)` na lista
3. `lambda/alexa/scene.py` — entrada em **`_ACTION_BY_ENDPOINT`**
4. `tests/test_lambda.py` — teste de que a cena publica **a sua** ação

O item 3 é o mais fácil de esquecer e o mais perigoso. Antes de existir a segunda cena, o
`scene.py` publicava `suspend` incondicionalmente e passava nos testes — quando a cena de
música entrou, ativá-la teria **suspendido o PC**, com o Lambda respondendo sucesso.

### B2. Dependência nova no agente

Se a sua ação precisa de um pacote novo, são **três** lugares, não um:

1. `agent/requirements.txt` — a declaração
2. `tools/check_requisitos.ps1` — o verificador, se o pacote for **obrigatório**
3. `docs/requisitos-e-variacoes.md` — se mudar o que o usuário precisa saber

O item 2 não é burocracia. O agente roda por `pythonw`, sem console: um `ModuleNotFoundError`
mata o processo em silêncio, a tarefa mostra "Running" por um instante e nada funciona, sem
erro em lugar nenhum. Foi o que quase aconteceu quando o `psutil` entrou.

Se o pacote for **opcional** — como os `winrt`, cuja ausência só faz o play/pause deixar de
existir —, o verificador deve reportar aviso e não falha, e o código precisa degradar sozinho.

### C. Interface nova da Alexa

Exemplo: o `PlaybackController`.

1. Ler a especificação da interface na doc da Amazon — o formato do `capabilities` varia
   (`properties.supported`, `supportedOperations`, `configuration`…)
2. `lambda/alexa/<interface>.py` — handler novo
3. `lambda/alexa/discovery.py` — declarar a capability no endpoint
4. `lambda/lambda_function.py` — rotear o namespace
5. Passos de (A) para o lado do agente
6. Testes

**Declare só o que você implementa de verdade.** O `PlaybackController` suporta oito operações;
declaramos cinco. O handler recusa explicitamente o que não declara, em vez de deixar virar
comportamento errado silencioso.

**Se for um mostrador e não um controle**, use `RangeController` com `nonControllable: true` e
registre a métrica em `lambda/alexa/metrics.py`, que é fonte única para o discovery e para o
report. Duas armadilhas do app estão em [problemas-encontrados.md](problemas-encontrados.md):
`unitOfMeasure` vira palavra em vez de símbolo, e nomes de capability precisam ser
pronunciáveis porque também são alvos de voz.

## O ciclo de implantação

```powershell
# 1. Testes locais — sem AWS, sem broker, sem Alexa
python tests\test_lambda.py
python tests\test_consistencia.py

# 2. Lambda
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy

# 3. Agente — obrigatório se mexeu em agent/ ou shared/
Stop-ScheduledTask -TaskName 'AlexaWOL Agent'
Start-ScheduledTask -TaskName 'AlexaWOL Agent'

# 4. Alexa — obrigatório se mexeu no discovery.py
#    No app: "Alexa, descobrir dispositivos"
```

Sobre o passo 4: **capacidade nova num endpoint existente não gera "dispositivo novo"**. O app
vai dizer que não encontrou nada, e está certo — o que mudou foi o que o dispositivo sabe
fazer. Para confirmar que a Alexa releu, procure o `Discover` no log e veja a resposta:

```powershell
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

## Verificar em camadas

Testar cada camada isolada é o que transforma "não funcionou" em um suspeito só:

| Camada | Como | Prova o quê |
|---|---|---|
| 1 | `python tests\test_lambda.py` | O handler monta o JSON certo |
| 1b | `python tests\test_consistencia.py` | As listas espelhadas continuam em sincronia |
| 2 | `python tools\send_cmd.py <acao>` | Broker, HMAC, agente e a ação no Windows |
| 3 | `aws lambda invoke` com uma diretiva | O Lambda publicado, sem depender da voz |
| 4 | Falar com a Alexa | Reconhecimento e roteamento da frase |

Quando falhar, o log do Lambda separa os mundos:

- **Diretiva não aparece** → a Alexa não roteou. Redescobrir dispositivos, ou a frase colide
  com um intent nativo.
- **Diretiva aparece e publica, mas nada acontece no PC** → agente. Quase sempre é reinício
  esquecido; senão, teste a camada 2.
- **Diretiva aparece com erro** → código do Lambda, e o traceback está no log.

## Antes de commitar

```powershell
python tests\test_lambda.py
python tests\test_consistencia.py
git status          # config.toml nao pode aparecer
```

Nunca preencha valores reais em arquivo versionado para rodar um comando — monte o `env.json`
fora da pasta do repositório. Já aconteceu duas vezes aqui, e as duas exigiram limpeza antes
do commit. Ver [problemas-encontrados.md](problemas-encontrados.md).

## Atualizar a documentação

Uma funcionalidade nova normalmente toca:

- `README.md` — tabela de comandos de voz
- `CLAUDE.md` — se houver decisão não óbvia que alguém possa "corrigir" por engano
- `docs/` — o guia da área, se houver

O critério para o `CLAUDE.md` é específico: registre o que parece um bug e não é. "Declaramos
só duas operações do `PlaybackController`" parece omissão — sem a explicação, o próximo
passante declara as oito e introduz o comportamento errado.
