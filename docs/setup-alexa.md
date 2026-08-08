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

Volte ao perfil LWA → **Web Settings** → **Allowed Return URLs** e cole **as três**. Faltando
uma, o vínculo falha exatamente no aplicativo que usa aquela região.

## 5.4 Habilitar e descobrir

1. No app Alexa: **Mais → Skills e Jogos → Suas Skills → Modo de Desenvolvedor** → `AlexaWOL`
   → **Ativar para uso**
2. Faça login com a mesma conta Amazon. É esse login que dispara o `AcceptGrant` — o Lambda
   guarda o refresh token no SSM naquele instante. Sem esse passo, o "ligar" não funciona,
   porque é o token que autoriza o envio do evento `WakeUp`.
3. **Descobrir dispositivos**

Devem aparecer dois: **Computador** e **Suspensão do computador**.

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

**O PC não liga, mas o resto funciona** — o caminho do "ligar" é totalmente distinto dos
demais: ele não passa pelo MQTT nem pelo agente. Verifique, nesta ordem:

1. `tools/wol_test.py` ainda acorda o PC? Se não, é hardware/BIOS, veja
   [setup-wol.md](setup-wol.md).
2. A Echo está na **mesma sub-rede** do PC? É requisito oficial. A Echo aqui está em
   `192.168.1.11` e o PC em `192.168.1.10` — mesma `/24`, correto.
3. O refresh token está no SSM (comando do passo 5.4)? Sem ele o evento `WakeUp` não é
   autorizado. Se estiver faltando, desative e reative a skill no app para refazer o
   `AcceptGrant`.
4. O log mostra `event gateway respondeu 202`? Qualquer coisa diferente disso indica token
   inválido ou endpoint errado.

**"O dispositivo não está respondendo"** — o agente caiu. O broker publica o *last will* e a
Alexa passa a reportar o PC como desligado. Confira:
`Get-ScheduledTask -TaskName 'AlexaWOL Agent' | Get-ScheduledTaskInfo`
