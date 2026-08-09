# 4. Lambda na AWS

A função precisa ficar em **`us-east-1`**. Não é preferência: pt-BR é servido por US East
(N. Virginia), e a Alexa simplesmente não entrega tráfego a um Lambda em outra região. Sua
conta está configurada com `sa-east-1` como padrão, então todos os comandos abaixo passam
`--region us-east-1` explicitamente.

O consumo cabe folgadamente no always-free do Lambda (1M requisições/mês), então o custo
recorrente é zero.

## A ordem que evita retrabalho

Este passo e o seguinte se entrelaçam: a AWS precisa do Skill ID, e a skill precisa do ARN do
Lambda. Não dá para fazer linear. Esta sequência minimiza as idas e vindas:

1. **Perfil Login with Amazon** ([setup-alexa.md](setup-alexa.md), passo 5.2) — leva 5 minutos
   e não depende de nada. Fazendo primeiro, você já tem o `LWA_CLIENT_ID` e o
   `LWA_CLIENT_SECRET` em mãos.
2. **4.1 e 4.2 aqui** — papel IAM e criação da função. Guarde o `FunctionArn`.
3. **4.3 aqui** — variáveis de ambiente, agora completas.
4. **Skill** ([setup-alexa.md](setup-alexa.md), passo 5.1) — aponte para o ARN, pegue o Skill ID.
5. **4.4 aqui** — `add-permission` com o Skill ID.
6. **Account linking** (passo 5.3) e cole as três Redirect URLs de volta no perfil LWA.

⚠️ O perfil LWA vive na sua **conta de desenvolvedor Amazon**, que não tem relação com a conta
AWS. Nada dele aparece no `aws` CLI, e nenhuma credencial da AWS serve ali. Use a mesma conta
Amazon em que a Echo está registrada.

## 4.1 Papel de execução

Os dois arquivos de política são descartáveis, então gere-os em `$env:TEMP` para não sujar o
repositório:

```powershell
$trust = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
$trustFile = Join-Path $env:TEMP 'alexawol-trust.json'
$trust | Out-File -Encoding ascii $trustFile

aws iam create-role --role-name alexawol-lambda-role `
    --assume-role-policy-document "file://$trustFile"

aws iam attach-role-policy --role-name alexawol-lambda-role `
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
```

O refresh token do account linking vive no SSM Parameter Store como SecureString, então o
papel precisa de acesso ao parâmetro e à chave KMS padrão do SSM:

```powershell
@'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:PutParameter"],
      "Resource": "arn:aws:ssm:us-east-1:123456789012:parameter/alexawol/*"
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:Encrypt"],
      "Resource": "*",
      "Condition": {"StringEquals": {"kms:ViaService": "ssm.us-east-1.amazonaws.com"}}
    }
  ]
}
'@ | Out-File -Encoding ascii (Join-Path $env:TEMP 'alexawol-ssm-policy.json')

aws iam put-role-policy --role-name alexawol-lambda-role `
    --policy-name alexawol-ssm `
    --policy-document "file://$(Join-Path $env:TEMP 'alexawol-ssm-policy.json')"
```

## 4.2 Criar a função

Empacote primeiro:

```powershell
powershell -ExecutionPolicy Bypass -File lambda\build.ps1
```

```powershell
aws lambda create-function `
    --function-name alexawol `
    --runtime python3.12 `
    --role arn:aws:iam::123456789012:role/alexawol-lambda-role `
    --handler lambda_function.lambda_handler `
    --zip-file fileb://lambda/alexawol.zip `
    --timeout 15 `
    --memory-size 256 `
    --region us-east-1
```

Timeout de 15 s dá margem: a Alexa corta em 8 s, mas o Lambda também renova token e fala com
o broker, e um cold start não deve derrubar a invocação inteira.

Anote o `FunctionArn` da saída — a skill vai apontar para ele.

## 4.3 Variáveis de ambiente

`LWA_CLIENT_ID` e `LWA_CLIENT_SECRET` só existem depois de criar o perfil Login with Amazon
(passo 5.2), então volte aqui depois. As demais você já tem:

```powershell
aws lambda update-function-configuration `
    --function-name alexawol --region us-east-1 `
    --environment 'Variables={
        PC_MAC=00-11-22-33-44-55,
        FRIENDLY_NAME=Computador,
        SUSPEND_FRIENDLY_NAME=Suspensão do computador,
        MUSIC_FRIENDLY_NAME=Música do computador,
        MQTT_HOST=SEU-CLUSTER.s1.eu.hivemq.cloud,
        MQTT_PORT=8883,
        MQTT_USERNAME=alexawol-lambda,
        MQTT_PASSWORD=SENHA-DO-LAMBDA,
        HMAC_SECRET=SEU-SEGREDO-HMAC,
        LWA_CLIENT_ID=amzn1.application-oa2-client.xxxx,
        LWA_CLIENT_SECRET=xxxx
    }'
```

O `HMAC_SECRET` precisa ser **idêntico** ao do `agent/config.toml`, e o `MQTT_USERNAME` aqui é
o `alexawol-lambda` (publicar em `cmd`, assinar em `state`) — não o do agente.

## 4.4 Autorizar a Alexa a invocar

Só dá para fazer depois de criar a skill, porque exige o ID dela. Volte aqui no fim do
passo 5.1:

```powershell
aws lambda add-permission `
    --function-name alexawol `
    --statement-id alexa-smarthome `
    --action lambda:InvokeFunction `
    --principal alexa-connectedhome.amazon.com `
    --event-source-token amzn1.ask.skill.SEU-SKILL-ID `
    --region us-east-1
```

Sem isso a Alexa recebe `AccessDeniedException` e o app mostra "não foi possível encontrar
dispositivos".

## Atualizar depois de mexer no código

```powershell
powershell -ExecutionPolicy Bypass -File lambda\build.ps1 -Deploy
```

## Depurar

```powershell
aws logs tail /aws/lambda/alexawol --follow --region us-east-1
```

O handler loga a diretiva recebida e a resposta enviada, o que costuma bastar para entender
qualquer recusa da Alexa.

## Próximo passo

[setup-alexa.md](setup-alexa.md)
