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
   e não depende de nada. Serve ao account linking, não às variáveis do Lambda.
2. **4.1 e 4.2 aqui** — papel IAM e criação da função. Guarde o `FunctionArn`.
3. **Skill** ([setup-alexa.md](setup-alexa.md), passo 5.1) — aponte para o ARN, pegue o Skill ID.
4. **4.4 aqui** — `add-permission` com o Skill ID.
5. **Account linking** (passo 5.3) e cole as três Redirect URLs de volta no perfil LWA.
6. **Send Alexa Events** (passo 5.3b) — ligue o toggle e copie o **Alexa Client Id/Secret**.
7. **4.3 aqui** — variáveis de ambiente, agora com as credenciais certas em mãos.
8. **Habilitar a skill** (passo 5.4) — é o login aqui que dispara o `AcceptGrant`.

O 4.3 fica no fim de propósito: o `LWA_CLIENT_ID`/`LWA_CLIENT_SECRET` que o Lambda precisa só
existem depois do passo 5.3b, e não são os do perfil criado no 5.2.

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

`LWA_CLIENT_ID` e `LWA_CLIENT_SECRET` só existem depois de ligar o toggle **Send Alexa Events**
([setup-alexa.md](setup-alexa.md), passo 5.3b), então faça aquele passo antes deste. As demais
você já tem:

Use um arquivo JSON, **não** a sintaxe abreviada `Variables={A=B,C=D}`. A abreviada quebra com
valores que têm espaço (`Suspensão do computador`) e com quebras de linha, e o erro que ela
produz não deixa claro qual variável causou o problema.

```powershell
$vars = @'
{
  "Variables": {
    "PC_MAC": "00-11-22-33-44-55",
    "MQTT_HOST": "SEU-CLUSTER.s1.eu.hivemq.cloud",
    "MQTT_PORT": "8883",
    "MQTT_USERNAME": "alexawol-lambda",
    "MQTT_PASSWORD": "SENHA-DO-LAMBDA",
    "HMAC_SECRET": "SEU-SEGREDO-HMAC",
    "LWA_CLIENT_ID": "amzn1.application-oa2-client.xxxx",
    "LWA_CLIENT_SECRET": "amzn1.oa2-cs.v1.xxxx"
  }
}
'@

# UTF-8 sem BOM, explicitamente. NÃO troque por `Out-File -Encoding utf8`: veja abaixo.
[System.IO.File]::WriteAllText("$PWD\env.json", $vars, (New-Object System.Text.UTF8Encoding $false))

aws lambda update-function-configuration `
    --function-name alexawol --region us-east-1 `
    --environment file://env.json

Remove-Item env.json   # contém segredos; não deixe na pasta
```

**Os nomes dos dispositivos não estão aqui de propósito.** `FRIENDLY_NAME`,
`SUSPEND_FRIENDLY_NAME` e `MUSIC_FRIENDLY_NAME` já têm os valores certos como padrão em
`lambda/config.py` — "Computador", "Suspensão do computador" e "Música do computador". O código
vai para o zip em UTF-8 e chega íntegro; passar os mesmos valores por variável de ambiente só
adicionaria um caminho onde o acento pode se perder, sem ganho nenhum.

Esse risco é concreto: numa tentativa anterior o `MUSIC_FRIENDLY_NAME` chegou à AWS como
`Msica do computador`, com o "ú" comido pela code page do console. Nada quebraria tecnicamente,
mas esse é o nome que aparece no app — e você teria que dizer "Alexa, ativar Msica do
computador" para funcionar.

Só defina essas variáveis se quiser nomes **diferentes** dos padrões. Se o nome tiver acento,
monte pelo codepoint para contornar a code page: `"M" + [char]0x00FA + "sica do computador"`.
Depois confira o que a AWS realmente guardou.

**Por que a escrita é assim e não `Out-File -Encoding utf8`.** No Windows PowerShell 5.1,
`-Encoding utf8` grava um BOM (`EF BB BF`) no começo do arquivo, e a AWS CLI rejeita o JSON com
`Unexpected UTF-8 BOM`. No PowerShell 7 o mesmo comando grava sem BOM, então o erro só aparece
para quem roda no 5.1 — e ambos costumam estar instalados na mesma máquina, o que torna a falha
intermitente conforme o terminal usado. O `UTF8Encoding $false` se comporta igual nas duas
versões.

⚠️ **`LWA_CLIENT_ID` e `LWA_CLIENT_SECRET` são os de "Alexa Skill Messaging"**, não os do
Security Profile do account linking. Eles ficam no console da skill em **Build → Permissions**,
atrás do botão SHOW, e só aparecem depois de ligar o toggle **Send Alexa Events** — ver
[setup-alexa.md](setup-alexa.md), passo 5.3b. O formato dos dois pares é idêntico, então usar o
errado não gera erro aqui: a falha só surge no "ligar o computador".

**Cole os valores do LWA por inteiro.** O `LWA_CLIENT_SECRET` vem no formato
`amzn1.oa2-cs.v1.` seguido de uma string hexadecimal — o prefixo faz parte do segredo, não é
rótulo. O mesmo vale para o `LWA_CLIENT_ID`, que é todo o `amzn1.application-oa2-client.xxxx`.
Cortar o prefixo produz uma falha só no "ligar", que é o único caminho que usa essas
credenciais.

O `HMAC_SECRET` precisa ser **idêntico** ao do `agent/config.toml`, e o `MQTT_USERNAME` aqui é
o `alexawol-lambda` (publicar em `cmd`, assinar em `state`) — não o do agente.

Conferir depois, sem expor os valores:

```powershell
aws lambda get-function-configuration --function-name alexawol --region us-east-1 `
    --query 'Environment.Variables | keys(@)'
```

## 4.4 Autorizar a Alexa a invocar

Só dá para fazer depois de criar a skill, porque exige o ID dela. Volte aqui no fim do
passo 5.1.

**Pegue o Skill ID real primeiro.** No Alexa Developer Console, na lista de skills, há um link
**View Skill ID** abaixo do nome; ele também aparece na URL. O formato é `amzn1.ask.skill.`
seguido de um **UUID com hífens**:

```
amzn1.ask.skill.a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Se o que você copiou não tiver hífens, não é o Skill ID.

```powershell
$skillId = 'amzn1.ask.skill.a1b2c3d4-e5f6-7890-abcd-ef1234567890'

aws lambda add-permission `
    --function-name alexawol `
    --statement-id alexa-smarthome `
    --action lambda:InvokeFunction `
    --principal alexa-connectedhome.amazon.com `
    --event-source-token $skillId `
    --region us-east-1
```

Confira o que ficou gravado — vale os cinco segundos:

```powershell
aws lambda get-policy --function-name alexawol --region us-east-1 `
    --query 'Policy' --output text | ConvertFrom-Json |
    Select-Object -ExpandProperty Statement |
    Select-Object Sid, @{n='Token';e={$_.Condition.StringEquals.'lambda:EventSourceToken'}}
```

### ⚠️ O erro que o placeholder provoca

Se você rodar o comando com o texto do placeholder em vez do ID real, a permissão é criada e o
comando **retorna sucesso** — mas ela não vale para skill nenhuma. E o sintoma aparece longe
dali: ao salvar o endpoint no console da Alexa, surge uma mensagem sobre **"event source
type"**, que não menciona token nem permissão.

A explicação: ao salvar o endpoint, o console consulta a política do Lambda e procura uma
permissão para `alexa-connectedhome.amazon.com` **com o Skill ID daquela skill**. Com o token
errado a verificação falha, e a Amazon reporta o erro de um jeito que despista.

Para corrigir, remova pelo `--statement-id` (não pelo conteúdo) e refaça:

```powershell
aws lambda remove-permission --function-name alexawol `
    --statement-id alexa-smarthome --region us-east-1
```

Sem a permissão correta, a Alexa recebe `AccessDeniedException`, o app mostra "não foi possível
encontrar dispositivos" e **o log group nem chega a existir** — porque o log só é criado na
primeira invocação, e ela nunca acontece.

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
