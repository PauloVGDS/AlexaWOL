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

**Pausar e continuar** — acrescentar `Alexa.PlaybackController` ao endpoint principal, mapeando
para as teclas de mídia do Windows (`keybd_event` com `VK_MEDIA_PLAY_PAUSE`). Funciona com
Spotify, YouTube e VLC de uma vez, porque todos respondem às teclas de mídia.
