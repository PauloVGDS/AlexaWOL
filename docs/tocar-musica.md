# Tocar uma música no PC pela rotina da Alexa

## O que não dá, e por quê

A Alexa **não consegue enviar o áudio dela para o PC**. Os únicos destinos de reprodução que
ela reconhece são dispositivos Echo, Fire TV e caixas pareadas por Bluetooth *ao Echo*. Não
existe interface no Smart Home API que transforme um PC Windows em saída de áudio da Alexa.

O `Alexa.Speaker` já implementado pode enganar nesse ponto: ele ajusta **nível de volume**, não
reproduz nada. É controle remoto de volume, não destino de áudio.

Um detalhe do setup confunde ainda mais: a Echo Show aparece como saída de som no PC
(`Speakers (Echo Show 5-3P4 Stereo)`, pareada por Bluetooth). Isso é o **PC mandando som para a
Echo** — o inverso do que se quer aqui.

**Quem toca a música é o PC, sozinho. A Alexa só dá o gatilho.**

```
"<sua frase>"
  └─ Rotina da Alexa
       ├─ (o passo que você já tem)
       └─ Casa inteligente: ativar "Música do computador"
            └─ Alexa Cloud → Lambda → MQTT → agente → shell do Windows abre a mídia
```

## A decisão de projeto que sustenta o resto

**A música mora na configuração do agente, não no Lambda nem na mensagem.** O comando que
trafega diz apenas `play_music`; qual mídia é essa, só o PC sabe.

Isso vale por três motivos. Trocar a música não exige redeploy do Lambda nem passar pelo
console da AWS. Caminhos de arquivo pessoais não saem da máquina. E, o mais importante, o
comando publicado continua sendo um verbo da allowlist — se a mídia viesse no payload, quem
tivesse o segredo HMAC faria o PC abrir qualquer programa.

## Configurar

Em `agent/config.toml`:

```toml
[media]
target = "spotify:playlist:37i9dQZF1DXcBWIGoYBM5M"
```

Aceita qualquer coisa que o Windows saiba abrir — quem resolve é o shell, então funciona sem
integrar com player nenhum:

| Tipo | Exemplo |
|---|---|
| Faixa do Spotify | `spotify:track:4cOdK2wGLETKBW3PvgPWqT` |
| Playlist do Spotify | `spotify:playlist:37i9dQZF1DXcBWIGoYBM5M` |
| YouTube | `https://www.youtube.com/watch?v=...` |
| Arquivo local | `C:\\Users\\<voce>\\Music\\musica.mp3` |

### Obter o URI do Spotify

No app: botão direito na faixa ou playlist → **Compartilhar** → **Copiar link**. Você recebe
`https://open.spotify.com/track/ID`. Converta para `spotify:track:ID`.

Vale a conversão: o formato `spotify:` abre o **app desktop**, enquanto o `https://` abre o
navegador e costuma parar numa página de login.

### Spotify instalado pela Microsoft Store

Validado nesta máquina: **funciona, e sem precisar do fallback.** Vale registrar porque a
suspeita era razoável — apps da Store não registram o protocolo na chave clássica
`shell\open\command`, e sim pelo mecanismo de ativação AppX. Mas `HKCU:\SOFTWARE\Classes\spotify`
carrega o valor `URL Protocol`, que é exatamente o que o ShellExecute procura, então o
`os.startfile` resolve sozinho.

O fallback para `cmd /c start` continua no código para os casos em que isso não vale.

## Testar

Sem envolver a Alexa, com o agente rodando:

```powershell
python tools\send_cmd.py play_music
```

Depois o handler do Lambda, isolado:

```powershell
python tests\test_lambda.py
```

## ⚠️ Por voz direta, o nome colide

**"Alexa, ativar música do computador" não funciona.** A Alexa toca música no próprio Echo.

"Música" é palavra reservada: o intent nativo de reprodução tem prioridade sobre nomes de
dispositivo, então a frase é capturada antes de chegar na cena. Testado — a cadeia técnica
responde certo quando a cena é acionada diretamente; o que falha é o reconhecimento da frase.

**Isso não afeta rotinas.** Dentro de uma rotina você escolhe o dispositivo numa lista, não por
voz, então o nome nunca é falado e a colisão não existe. Para uma música fixa, essa é a forma
de usar.

Se um dia você quiser chamar por voz, renomeie a cena pela variável `MUSIC_FRIENDLY_NAME` do
Lambda, evitando "música", "som", "tocar", "playlist" e "rádio" — todas disputam com intents
nativos. Algo como "Trilha do computador" funciona.

## Montar a rotina

1. App Alexa → **Mais → Rotinas** → abra a rotina que você já tem
2. **Adicionar ação** → **Casa inteligente** → **Música do computador** → Ativar

Vale acrescentar, antes dela, uma ação de **Casa inteligente → Computador** ajustando o volume.
Isso já funciona com o `Alexa.Speaker` implementado e não precisa de código novo. É útil porque
com o PC no mudo a música toca em silêncio e parece que falhou.

## Se o PC estiver desligado

A rotina precisa de três passos **nesta ordem**:

1. Casa inteligente: ligar o Computador
2. **Aguardar 40 a 60 segundos** — rotinas da Alexa têm passo de espera
3. Casa inteligente: ativar Música do computador

Sem a espera, a cena dispara antes de o agente conectar no broker: o Lambda publica em
`alexawol/cmd` e não há ninguém assinando o tópico. O comando se perde em silêncio.

O tempo exato depende do boot e do logon. O agente sobe na sessão do usuário, então se a
máquina para na tela de bloqueio esperando senha, ele não conecta nunca. Meça no seu caso antes
de fixar o número.

## Extensões

**Várias músicas** — um endpoint-cena por música, cada um com entrada no mapa de
`lambda/alexa/scene.py` e no `[media]` da config. Cresce linearmente; passando de umas poucas,
vale repensar para um parâmetro em vez de um endpoint por faixa.

**Pausar e continuar** — ver a seção abaixo: exige o SMTC do Windows, ao custo de uma
dependência WinRT.

## Controlar a reprodução

Via `Alexa.PlaybackController` no endpoint principal:

| Frase | Operação |
|---|---|
| "Alexa, continuar no computador" | `Play` |
| "Alexa, pausar no computador" | `Pause` |
| "Alexa, próxima no computador" | `Next` |
| "Alexa, anterior no computador" | `Previous` |
| "Alexa, recomeçar no computador" | `StartOver` |

### Funciona com qualquer player, não só o Spotify

O agente usa o **SMTC** (`GlobalSystemMediaTransportControlsSessionManager`), a API de sessão de
mídia do Windows — a mesma que alimenta aquele overlay que aparece ao apertar as teclas de
volume. Não há nada específico de Spotify no código.

Qualquer aplicativo que se integre ao SMTC aparece ali, e a integração é o padrão hoje:
navegadores tocando YouTube ou Netflix, VLC, Groove, iTunes, Windows Media Player. Se você vê o
app no overlay de mídia do Windows, o AlexaWOL controla.

Duas ressalvas honestas:

- **O SMTC controla a sessão *atual***. Com dois players tocando ao mesmo tempo, o comando vai
  para aquele que o Windows considera ativo — normalmente o último que você usou.
- **Sem nenhuma mídia aberta não há sessão.** `Play` e `Pause` falham com mensagem clara em vez
  de fazer algo aleatório.

Para o caso raro de um player que registra o atalho global de mídia sem se integrar ao SMTC, o
agente cai nas teclas de mídia (`keybd_event`). Avançar e voltar continuam funcionando; `Play` e
`Pause`, não — e é de propósito, pelo motivo abaixo.

### Por que play/pause exige o SMTC

O Windows tem **uma única tecla** de play/pause (`VK_MEDIA_PLAY_PAUSE`), que **alterna**. A
Alexa trata `Play` e `Pause` como operações distintas. Mapear as duas na mesma tecla erraria
metade das vezes: "pausar" com a música já pausada faria ela **voltar a tocar**.

O SMTC tem `try_play_async` e `try_pause_async` explícitos. Verificado nesta máquina:

```
play()  com a música já tocando  -> continua tocando   (a alternância teria pausado)
pause() com a música já pausada  -> continua pausada   (a alternância teria retomado)
```

### Por que "anterior" e "recomeçar" são ações diferentes

Um comando de "anterior" **rebobina a faixa atual** em vez de trocar, se já se passaram alguns
segundos — regra do Spotify e da maioria dos players. Quem quer voltar de verdade precisa de um
segundo comando.

O SMTC resolve isso lendo a posição de reprodução: passado o limiar de 3 segundos o agente
manda dois comandos; antes dele, um só já troca de faixa. Sem o SMTC sobra o toque duplo às
cegas, que retrocede duas faixas quando a atual acabou de começar.

`StartOver` usa busca explícita para a posição zero quando o player suporta, o que é
inequívoco.
