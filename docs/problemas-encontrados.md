# Problemas encontrados até tudo funcionar

Registro dos tropeços reais desta instalação — o que falhou, por que, e como reconhecer. Boa
parte não estava em lugar nenhum da documentação oficial, e vários só se manifestaram longe da
causa.

O padrão que se repete: **falhas silenciosas**. Comando retorna sucesso, log não acusa nada, e
o sintoma aparece três camadas adiante. Por isso a coluna "como reconhecer" importa mais que a
correção.

## Índice por sintoma

| O que você vê | Causa real | Seção |
|---|---|---|
| Tudo funciona **menos ligar o PC** | Credenciais LWA erradas, ou toggle Send Alexa Events desligado | [Alexa](#o-console-da-alexa) |
| App: "não foi possível encontrar dispositivos" | Falta `add-permission` no Lambda | [Alexa](#o-console-da-alexa) |
| Console: erro sobre **"event source type"** | `add-permission` gravado com o placeholder literal | [Alexa](#o-console-da-alexa) |
| HTTP 400 `bad-redirect-uri-vendor` ao vincular | Redirect URLs não cadastradas no perfil LWA | [Alexa](#o-console-da-alexa) |
| Log group do Lambda não existe | A função nunca foi invocada — não é erro | [AWS](#aws-e-linha-de-comando) |
| `ParameterNotFound` num parâmetro que existe | Git Bash converteu o caminho iniciado em `/` | [Terminal](#terminal-e-codificação) |
| AWS CLI: `Unexpected UTF-8 BOM` | `Out-File -Encoding utf8` no PowerShell 5.1 | [Terminal](#terminal-e-codificação) |
| Nome do dispositivo perdeu o acento | Code page do console comeu o caractere | [Terminal](#terminal-e-codificação) |
| `send_cmd.py` publica "com sucesso" e o agente não recebe | ACL do broker recusa — credencial errada | [Nossos bugs](#bugs-nossos) |
| "Alexa, ativar música do computador" toca no Echo | "Música" colide com intent nativo | [Alexa](#o-console-da-alexa) |
| `AttributeError: 'AudioDevice' object has no attribute 'Activate'` | API do pycaw mudou | [Windows](#windows) |

---

## Arquitetura: a premissa errada que quase custou hardware

**O erro:** parti do princípio de que, com o PC desligado, seria preciso um dispositivo sempre
ligado na rede — ESP32, Raspberry Pi ou port-forward no roteador — para enviar o magic packet.
Cheguei a levantar o toolchain embarcado da máquina para planejar isso.

**A realidade:** a Amazon tem a interface oficial `Alexa.WakeOnLANController`, em que **a própria
Echo transmite o magic packet na rede local**. Zero infraestrutura, zero hardware extra. A
única exigência é a Echo estar na mesma sub-rede do PC.

**Como quase erramos de novo:** a alternativa que parecia óbvia era emulação local — fazer um
dispositivo se passar por lâmpada Hue ou WeMo. A pesquisa mostrou que seria a escolha errada:
a emulação **WeMo** sobrevive mas é liga/desliga apenas (o Echo nem envia comando de dimmer, então
volume percentual é impossível), e a emulação **Hue**, que daria percentual, está quebrando —
a Amazon apertou a validação SSDP por volta de agosto de 2025, e a issue correspondente do Home
Assistant foi fechada como *not planned*.

**Lição:** antes de aceitar uma restrição de arquitetura, procure a API oficial. A diferença
aqui foi entre comprar hardware e não escrever linha nenhuma de código para o caminho mais
crítico.

---

## Windows

### A API do pycaw mudou e todo tutorial da internet está desatualizado

**Sintoma:** `AttributeError: 'AudioDevice' object has no attribute 'Activate'`

O padrão que aparece em praticamente toda referência online não funciona mais:

```python
speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)   # quebrado
```

A partir da versão `20251023`, `AudioUtilities.GetSpeakers()` devolve um `AudioDevice` com a
propriedade pronta:

```python
AudioUtilities.GetSpeakers().EndpointVolume    # funciona
```

Descoberto ao rodar, não ao ler. O `requirements.txt` fixa `pycaw>=20251023` por isso.

### Core Audio é isolado na sessão 0 — o agente não pode ser SYSTEM

O plano original instalava o agente como serviço SYSTEM no boot. Isso **não funcionaria**: o
Core Audio do Windows é isolado na sessão 0, e um processo SYSTEM não consegue ler nem escrever
o volume.

A tarefa agendada roda na sessão do usuário, com gatilho de logon. Não é limitação prática:
ao acordar do S3 a sessão continua viva mesmo bloqueada, e o "ligar" nunca depende do agente.

### Suspender é S3 de verdade, ao contrário do que se diz

Circula a ressalva de que, com hibernação habilitada, o Windows hibernaria (S4) em vez de
suspender. **Medido aqui: não acontece.** O par de eventos 42/107 do log do sistema confirma S3
com a hibernação ativa. Não é preciso `powercfg -h off`.

Depende de firmware e drivers, então vale remedir em outra máquina — mas não assuma o pior sem
testar.

---

## Terminal e codificação

Três armadilhas distintas, todas produzindo erros que não mencionam codificação nem caminho.

### Git Bash converte caminhos iniciados com `/`

**Sintoma:** `ParameterNotFound` num parâmetro SSM que existe. Ou uma consulta de log que volta
vazia com o log group presente.

O Git Bash converte argumentos que parecem caminho absoluto POSIX em caminho Windows. Então
`/alexawol/refresh_token` chega à AWS CLI deformado, e `/aws/lambda/alexawol` idem.

```bash
aws ssm get-parameter --name /alexawol/refresh_token    # ParameterNotFound (mentira)
```

```powershell
aws ssm get-parameter --name "/alexawol/refresh_token"  # funciona
```

**Custou tempo duas vezes nesta instalação**, com conclusões opostas em cada uma: uma vez fez
parecer que o Lambda nunca tinha sido invocado, outra fez parecer que o account linking tinha
falhado quando já estava pronto. Use PowerShell para qualquer argumento que comece com `/`.

### `Out-File -Encoding utf8` grava BOM no PowerShell 5.1

**Sintoma:** `Unexpected UTF-8 BOM (decode using utf-8-sig)` da AWS CLI ao passar `file://`.

Medido nesta máquina, que tem as duas versões:

```
pwsh 7.6.4          -Encoding utf8  →  7B 22 61    sem BOM, funciona
powershell.exe 5.1  -Encoding utf8  →  EF BB BF    com BOM, quebra
```

A AWS CLI faz `json.loads` do conteúdo, e o Python recusa o BOM. O modo de falha é **intermitente**:
funciona num terminal e falha no outro, sem nada indicar codificação.

```powershell
[System.IO.File]::WriteAllText("$PWD\env.json", $json, (New-Object System.Text.UTF8Encoding $false))
```

Esse `UTF8Encoding $false` se comporta igual nas duas versões.

### A code page do console come acentos

**Sintoma:** o `MUSIC_FRIENDLY_NAME` chegou à AWS como `Msica do computador`. Nada quebra
tecnicamente — mas é o nome que aparece no app, e só responderia a "Alexa, ativar Msica do
computador".

A correção não foi montar a string por codepoint, e sim **não passar esses valores**: os nomes
já têm o valor certo como padrão em `lambda/config.py`, que vai para o zip em UTF-8 e chega
íntegro. Definir por variável de ambiente o mesmo valor que já é o padrão só criava um caminho
onde o acento pode se perder.

**Lição geral:** o melhor conserto para um caminho frágil costuma ser eliminá-lo, não blindá-lo.

---

## AWS e linha de comando

### `Variables={A=B,C=D}` quebra com espaço e acento

A sintaxe abreviada do `--environment` não sobrevive a valores como `Suspensão do computador`,
e o erro não diz qual variável causou o problema. Use um arquivo JSON com `file://`.

### `update-function-configuration` substitui o conjunto inteiro

Não é merge. Omitir uma variável a apaga. Sempre parta do estado atual:

```powershell
aws lambda get-function-configuration --function-name alexawol --region us-east-1 `
    --query 'Environment.Variables'
```

### Log group ausente não é erro — é sintoma

O log group do Lambda é criado na **primeira invocação**, não na criação da função. Ele não
existir significa que a função **nunca foi chamada** — quase sempre porque falta o
`add-permission`. Isso é diagnóstico, não problema.

### A região é obrigatória e não é a do seu perfil

pt-BR é servido por US East (N. Virginia). O Lambda **tem** que ficar em `us-east-1`, e o perfil
padrão desta máquina aponta para `sa-east-1`. Todo comando precisa de `--region us-east-1`
explícito. Criar no lugar errado não dá erro nenhum — a skill simplesmente nunca é invocada.

---

## O console da Alexa

Onde estão as armadilhas piores, porque quase todas falham em silêncio.

### `add-permission` aceita qualquer string como Skill ID

**Sintoma:** ao salvar o endpoint no console, um erro sobre **"event source type"**.

O `--event-source-token` aceita o texto do placeholder e **retorna sucesso**. A permissão é
criada e não vale para skill nenhuma. O console, ao salvar o endpoint, consulta a política do
Lambda procurando o Skill ID daquela skill; não achando, reporta um erro que não menciona token
nem permissão.

O que resolve na hora: **o Skill ID real é um UUID com hífens**. Se o que você colou não tem
hífens, não é o Skill ID.

### As Redirect URLs precisam voltar para o perfil LWA

**Sintoma:** HTTP 400 com `lwa-invalid-parameter-bad-redirect-uri-vendor` ao vincular a conta.

Depois de salvar o Account Linking, o console mostra três Redirect URLs. Elas precisam ser
coladas de volta no perfil LWA, em **Web Settings → Allowed Return URLs**. As três — cadastrar
só a da sua região deixa a armadilha montada para quando o app cair em outro host.

A URL recusada vem na própria mensagem de erro, e como o vendor ID é o mesmo nas três, dá para
derivar as outras trocando só o host.

### O passo que não está em lugar nenhum: **Send Alexa Events**

Este é o que bloqueou o projeto por mais tempo, e não constava da nossa documentação.

Sem o toggle **Send Alexa Events** ligado em **Build → Permissions**, a Alexa **não envia o
`AcceptGrant`**. Sem `AcceptGrant` não há refresh token, e sem ele não há como postar o evento
`WakeUp`. Todo o resto — volume, desligar, suspender, música, discovery — funciona
normalmente, então nada indica que a permissão falta.

### E as credenciais que ele revela são OUTRAS

Ao ligar o toggle aparece a seção **Alexa Skill Messaging**, com **Alexa Client Id** e **Alexa
Client Secret** atrás de um botão SHOW.

**Essas são as que vão no Lambda** — não as do Security Profile usado no Account Linking. Da
documentação da Amazon:

> *the client_id and client_secret are **not** the ones used by the skill that have been set up
> using "Login with Amazon", but rather from the "Alexa Skill Messaging"*

Os dois pares têm formato idêntico (`amzn1.application-oa2-client.…`), então a troca não gera
erro em lugar nenhum da configuração. **A falha aparece só no "ligar"**, porque é o único
caminho que troca o código do `AcceptGrant` por tokens. São papéis distintos: o Security Profile
autentica **o usuário** no vínculo; o Alexa Skill Messaging autentica **a skill** perante o
event gateway.

### O `AcceptGrant` só chega no momento do vínculo

Corrigir as credenciais não basta. Numa skill já vinculada, o `AcceptGrant` não é reenviado
sozinho — é preciso **desabilitar e reabilitar** a skill no app, refazendo o login.

### "Música" no nome da cena colide com o intent nativo

**Sintoma:** "Alexa, ativar música do computador" faz a Echo tocar música nela mesma.

"Música" é palavra reservada. O intent nativo de reprodução tem prioridade sobre nomes de
dispositivo, e a frase é capturada antes de chegar na skill. O mesmo vale para *som*, *tocar*,
*playlist* e *rádio*.

**Rotinas não sofrem disso**, porque ali o dispositivo é escolhido numa lista e o nome nunca é
falado. Para uma mídia fixa, é assim que se usa.

### A ordem do setup é circular

A skill precisa do ARN do Lambda; o `add-permission` precisa do Skill ID que só nasce com a
skill criada; e as variáveis de ambiente dependem de credenciais que só existem depois do
toggle. Não há sequência linear — a ordem em `setup-aws.md` minimiza as idas e vindas, mas não
as elimina.

---

## Bugs nossos

### `scene.py` ignorava o `endpointId` — a segunda cena teria suspendido o PC

O handler publicava `suspend` incondicionalmente. Passava despercebido enquanto existia uma
única cena. No instante em que a cena de música entrou, **"ativar música do computador" teria
suspendido o computador** — e o Lambda responderia sucesso, com a Alexa confirmando por voz.

Corrigido com um mapa de endpoint para ação, e `NO_SUCH_ENDPOINT` para endpoint desconhecido em
vez de cair num padrão. O teste que pega a regressão verifica que **cada cena publica a sua
ação**.

**Lição:** um valor hardcoded que "funciona porque só existe um caso" é uma bomba-relógio. O
teste certo não é "a cena funciona", é "cada cena faz a coisa certa".

### `send_cmd.py` usava a credencial errada e falhava no broker

A ferramenta faz o papel do Lambda e precisa **publicar** em `alexawol/cmd`, mas lia as
credenciais do agente — que pela ACL só pode assinar. O script reportava publicação
bem-sucedida e o agente nunca recebia nada, porque a rejeição acontece no broker.

A saída óbvia seria conceder publish ao agente durante os testes e remover depois. Recusada:
*"lembre de remover a permissão"* é um passo que quase nunca acontece, e a ACL ficaria
permanentemente mais fraca justamente na fronteira que o projeto protege. Foi criada uma seção
`[publisher]` opcional, com a credencial do Lambda.

### `DeferredResponse` é inviável no Lambda

A documentação descreve o "ligar" como DeferredResponse → evento `WakeUp` → resposta final.
Isso não funciona: o Lambda **congela ao retornar**, então não há como enviar o evento "depois".

O que funciona é postar o evento durante a invocação e retornar a `Alexa.Response` normal.

---

## Segurança

### O `.gitignore` não protege contra sincronização

O `config.toml` — que concentra as duas credenciais MQTT e o segredo HMAC — estava em
`agent/`, dentro da árvore do projeto. E **este projeto vive dentro do OneDrive**.

O `.gitignore` impedia o arquivo de ir para o repositório e não fazia nada quanto ao OneDrive,
que o sincronizava para a nuvem da Microsoft e para todo dispositivo da conta. Era exatamente o
"sair da máquina" que o modelo de ameaça proibia.

Movido para `%LOCALAPPDATA%\AlexaWOL\config.toml`, que nenhum serviço de sincronização cobre. E
como mudar o padrão não impede alguém de recriar o arquivo no lugar errado, o agente e o
`send_cmd.py` **detectam e avisam** se o config carregado estiver sob OneDrive, Dropbox, Google
Drive ou iCloud.

**Consequência que permanece:** as credenciais que estiveram sincronizadas devem ser
rotacionadas. Mover o arquivo não desfaz o que já subiu.

### Segredos reais foram parar num arquivo versionado — duas vezes

Valores reais foram preenchidos direto no bloco de exemplo do `docs/setup-aws.md` para rodar os
comandos. Nas duas vezes ficou só na árvore de trabalho e nunca entrou em commit — verificado
varrendo todos os blobs do repositório, incluindo objetos órfãos.

**A causa é o padrão, não o descuido:** preencher um arquivo versionado para executar algo.
Monte o `env.json` fora da pasta do repositório.

### Senhas iguais anulam a separação de credenciais

As duas credenciais MQTT foram criadas com a mesma senha. A ACL do HiveMQ é por usuário, então
nada quebra no broker — mas destrói a única propriedade que justifica ter duas credenciais. Os
nomes de usuário são previsíveis; com a mesma senha, quem obtém a do agente obtém junto a de
publicar comandos.

---

## O que este projeto ensinou sobre depurar

**Os dois caminhos são independentes.** "Ligar" não passa pelo MQTT nem pelo agente; todo o
resto não passa pelo event gateway. Saber disso transforma um sintoma em diagnóstico: *tudo
funciona menos ligar* aponta para credenciais LWA ou account linking, nunca para rede ou BIOS.

**Teste cada camada isolada, na ordem em que uma valida a anterior.** Wake-on-LAN por app de
celular antes de existir skill. Agente por `send_cmd.py` antes de existir Lambda. Lambda por
`test_lambda.py` antes de existir Alexa. Sem isso, uma falha no fim tem cinco suspeitos.

**Desconfie de sucesso silencioso.** `add-permission` com token inválido, `send_cmd.py`
publicando contra a ACL, `AcceptGrant` que nunca é enviado — todos retornam sucesso. Quando um
passo "deu certo" mas o efeito não aparece, verifique o efeito, não o retorno.

**Confirme a leitura antes de confiar na conclusão.** Duas vezes uma consulta deformada pelo
shell produziu diagnóstico errado, e nas duas a conclusão parecia coerente com o resto.
