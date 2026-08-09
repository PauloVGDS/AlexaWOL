# 5. Skill no Alexa Developer Console

Um esclarecimento antes de começar, porque é fonte comum de confusão: **Smart Home Skill não é
uma skill pronta da loja**. É uma *categoria* de skill que você mesmo escreve e publica apenas
para a sua conta, em modo desenvolvedor. Ela nunca vai para a loja, não passa por certificação
e não tem dono cobrando mensalidade — o servidor é o seu Lambda.

⚠️ **Use a mesma conta Amazon em que a Echo está registrada.** Skill em modo desenvolvedor só
habilita em dispositivos dessa conta. Com contas diferentes, tudo parece certo e nada funciona.

## 5.1 Criar a skill

1. <https://developer.amazon.com/alexa/console/ask> → **Create Skill**
2. Nome: `AlexaWOL`. Idioma principal: **Português (BR)**
3. Modelo: **Smart Home**. Método de hospedagem: **Provision your own**
4. Em **Smart Home service endpoint**, cole o ARN do Lambda (`Default endpoint`)
5. Copie o **Skill ID** (`amzn1.ask.skill.…`) e volte ao passo 4.4 do
   [setup-aws.md](setup-aws.md) para autorizar a invocação

## 5.2 Login with Amazon

O account linking é obrigatório em Smart Home skills. É gratuito e o próprio LWA faz o papel
de servidor OAuth — você não precisa hospedar nada.

1. <https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html>
2. **Create a New Security Profile**: nome `AlexaWOL`, descrição e uma URL de política de
   privacidade qualquer (pode ser um link seu; não é validado para skill não publicada)
3. Anote o **Client ID** e o **Client Secret** e coloque nas variáveis de ambiente do Lambda
   (passo 4.3)

## 5.3 Ligar os dois

No console da skill, em **Account Linking**:

| Campo | Valor |
|---|---|
| Authorization URI | `https://www.amazon.com/ap/oa` |
| Access Token URI | `https://api.amazon.com/auth/o2/token` |
| Client ID | do perfil LWA |
| Client Secret | do perfil LWA |
| Scheme | HTTP Basic (Recommended) |
| Scope | `profile:user_id` |

Salve. A página vai mostrar três **Redirect URLs** (`https://pitangui.amazon.com/…`,
`https://layla.amazon.com/…`, `https://alexa.amazon.co.jp/…`).

Todas seguem o formato `https://<host>/api/skill/link/<SEU-VENDOR-ID>`, com o mesmo vendor ID
nas três — muda só o host: `pitangui` (América do Norte), `layla` (Europa) e `alexa.amazon.co.jp`
(Extremo Oriente).

Volte ao perfil LWA → **Web Settings** → **Edit** → **Allowed Return URLs** e cole **as três**,
cada uma numa entrada separada. Três cuidados, porque o LWA compara string literal: sem barra
no final, sem espaço invisível colado na cópia, e exatamente como o console da skill mostra.

### ⚠️ O erro que aparece se você pular isto

```
lwa-invalid-parameter-bad-redirect-uri-vendor
```

É um HTTP 400 ao tentar vincular a conta no app. Significa que o LWA recebeu um `redirect_uri`
que não está na lista de retorno autorizada do Security Profile. **A URL recusada vem na
própria mensagem de erro** — dá para derivar as outras duas trocando o host, já que o vendor ID
é o mesmo nas três.

Cadastrar só a da sua região resolve o sintoma imediato mas deixa a armadilha montada: se o app
cair em outro host, ou você usar o site em vez do celular, o vínculo falha de novo e parece
aleatório, funcionando num lugar e não em outro. Cole as três de uma vez.

Depois de salvar, espere um ou dois minutos antes de tentar de novo — a alteração no LWA não
propaga instantaneamente.

#### Se o erro persistir com as três URLs cadastradas

Repare no sufixo: `bad-redirect-uri-`**`vendor`**. Ele não diz apenas "URL não cadastrada" — diz
que o *vendor* da URL não corresponde ao vendor associado ao `client_id`. Isso aponta para uma
causa diferente, e a mais provável é **o Security Profile estar numa conta Amazon diferente da
que é dona da skill**. O vendor ID embutido nas Redirect URLs é o da conta da skill; se o perfil
LWA nasceu em outra conta, nenhuma URL cadastrada nele vai bater.

Confira o e-mail logado nos dois consoles, em abas separadas:

- <https://developer.amazon.com/alexa/console/ask> — onde está a skill
- <https://developer.amazon.com/loginwithamazon/console/site/lwa/overview.html> — onde está o perfil

Se forem contas diferentes, recrie o Security Profile na conta certa e troque o
`client_id`/`secret` em **dois** lugares: no Account Linking da skill e nas variáveis de
ambiente do Lambda.

Se forem a mesma conta, verifique nesta ordem:

1. **É o perfil certo?** Havendo mais de um Security Profile, o que importa é aquele cujo
   Client ID bate com o `LWA_CLIENT_ID` da função. Abra Web Settings e confira o Client ID antes
   de olhar as URLs.
2. **É o campo certo?** **Allowed Return URLs** é o que vale. **Allowed Origins** fica logo ao
   lado, não serve para este fluxo e é fácil confundir.
3. **Persistiu?** Recarregue a página e veja se as três continuam lá. O LWA às vezes aceita o
   clique em Save sem gravar quando falta algum campo obrigatório do perfil — a Privacy Notice
   URL em especial.

Não vale tentar diagnosticar isso disparando requisições ao endpoint OAuth por script: a Amazon
recusa requisição que não vem de navegador, devolvendo 400 tanto para configuração certa quanto
errada. O teste não distingue nada e só parece sondagem.

## 5.3b Permissão para enviar eventos — **sem isto o "ligar" não funciona**

Este passo é fácil de não descobrir, porque nada no console indica que ele falta e a skill
funciona quase inteira sem ele.

No console da skill, painel esquerdo → **PERMISSIONS** → ligue o toggle **Send Alexa Events**.

Sem essa permissão a Alexa **não envia o `AcceptGrant`**. Sem o `AcceptGrant` não há refresh
token, e sem refresh token não há como postar o evento `WakeUp`. Todo o resto — volume,
desligar, suspender, música, discovery — continua funcionando normalmente, porque nada disso
passa pelo event gateway.

### ⚠️ As credenciais aqui são OUTRAS

Ao ligar o toggle aparece a seção **Alexa Skill Messaging**, com um botão **SHOW** que revela
**Alexa Client Id** e **Alexa Client Secret**.

**São essas que vão nas variáveis `LWA_CLIENT_ID` e `LWA_CLIENT_SECRET` do Lambda** — não as do
Security Profile que você usou no Account Linking. Da documentação da Amazon:

> *the client_id and client_secret are **not** the ones used by the skill that have been set up
> using "Login with Amazon" (Build > Account Linking), but rather from the "Alexa Skill
> Messaging" (Build > Permissions > Alexa Skill Messaging)*

Os dois pares têm formato idêntico (`amzn1.application-oa2-client.…`), então trocar um pelo
outro não gera erro em lugar nenhum da configuração. A falha aparece só depois, e só no
"ligar". São papéis diferentes: o Security Profile autentica **o usuário** no vínculo da conta;
o Alexa Skill Messaging autentica **a skill** perante o event gateway.

Atualize as duas variáveis com os valores corretos ([setup-aws.md](setup-aws.md), passo 4.3) e
então **desabilite e reabilite a skill no app** — o `AcceptGrant` só é enviado no momento do
vínculo, então com a skill já vinculada ele não chega sozinho.

## 5.4 Habilitar e descobrir

1. No app Alexa: **Mais → Skills e Jogos → Suas Skills → Modo de Desenvolvedor** → `AlexaWOL`
   → **Ativar para uso**
2. Faça login com a mesma conta Amazon. É esse login que dispara o `AcceptGrant` — o Lambda
   guarda o refresh token no SSM naquele instante. Sem esse passo, o "ligar" não funciona,
   porque é o token que autoriza o envio do evento `WakeUp`.
3. **Descobrir dispositivos**

Devem aparecer três: **Computador**, **Suspensão do computador** e **Música do computador**.

Confirme que o token foi salvo:

```powershell
aws ssm get-parameter --name /alexawol/refresh_token --with-decryption `
    --region us-east-1 --query 'Parameter.Version'
```

## 5.5 Os comandos

| Frase | O que faz |
|---|---|
| "Alexa, ligar o computador" | A Echo transmite o magic packet na rede local |
| "Alexa, desligar o computador" | Desliga (S5), com janela de cancelamento |
| "Alexa, ativar suspensão do computador" | Suspende (S3) |
| "Alexa, ativar música do computador" | Abre a mídia configurada — ver [tocar-musica.md](tocar-musica.md) |
| "Alexa, colocar o volume do computador em 30" | Volume absoluto |
| "Alexa, aumentar o volume do computador em 20" | Ajuste relativo |
| "Alexa, silenciar o computador" | Mudo |

Para frases mais curtas, crie **Rotinas** no app: "Alexa, bom dia" → ligar o computador. As
rotinas são gratuitas e resolvem o nome longo da cena de suspensão.

## Quando algo não funciona

**"Não encontrei nenhum dispositivo"** — quase sempre é o passo 4.4 faltando. Confira o log:

```powershell
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

Se nenhuma invocação aparece, o problema é a permissão. Se aparece e a resposta tem erro, o
problema é o código.

**O PC não liga, mas o resto funciona** — essa combinação exata é informativa, não coincidência.
As credenciais LWA são usadas em um único caminho do código: `get_access_token()` só é chamado
por `send_wake_up()`, que só é usado pelo `TurnOn`. Volume, desligar, suspender, música,
discovery e ReportState nunca tocam nesse módulo.

Então, se **tudo funciona menos ligar**, suspeite primeiro do `LWA_CLIENT_ID` / `LWA_CLIENT_SECRET`
nas variáveis de ambiente do Lambda, ou do account linking. Verifique nesta ordem:

1. `tools/wol_test.py` ainda acorda o PC? Se não, é hardware/BIOS, veja
   [setup-wol.md](setup-wol.md).
2. A Echo está na **mesma sub-rede** do PC? É requisito oficial. A Echo aqui está em
   `192.168.1.11` e o PC em `192.168.1.10` — mesma `/24`, correto.
3. O refresh token está no SSM (comando do passo 5.4)? Sem ele o evento `WakeUp` não é
   autorizado. Se estiver faltando, desative e reative a skill no app para refazer o
   `AcceptGrant` — e olhe o log, porque `handle_accept_grant` devolve o motivo como
   `ACCEPT_GRANT_FAILED`.
4. O log mostra `event gateway respondeu 202`? Qualquer coisa diferente disso indica token
   inválido ou endpoint errado.

**"O dispositivo não está respondendo"** — o agente caiu. O broker publica o *last will* e a
Alexa passa a reportar o PC como desligado. Confira:
`Get-ScheduledTask -TaskName 'AlexaWOL Agent' | Get-ScheduledTaskInfo`
