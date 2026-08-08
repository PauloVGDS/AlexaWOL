# 2. HiveMQ Cloud Serverless

A ponte que leva os comandos da nuvem até o PC. Gratuito para sempre, sem cartão, com
autenticação de verdade — TLS, usuário/senha e ACL por tópico. Limites: 100 conexões e
10 GB/mês, muito acima do que este projeto consome. Não há exclusão por inatividade, o que
foi o motivo de preferi-lo ao EMQX (que para o cluster após 30 dias parado) e ao Supabase
(que pausa o projeto após 7 dias).

## Criar o cluster

1. Cadastre-se em <https://console.hivemq.cloud/> e crie um cluster **Serverless / Free**.
2. Anote o **hostname** (algo como `abc123def.s1.eu.hivemq.cloud`) e a porta **8883**.

## Criar duas credenciais separadas

Em **Access Management**, crie dois usuários. A separação importa: se a credencial do Lambda
vazar, ela não consegue nem ler o estado do seu PC, muito menos escutar comandos.

| Usuário | Permissão | Tópico |
|---|---|---|
| `alexawol-lambda` | Publish | `alexawol/cmd` |
| `alexawol-lambda` | Subscribe | `alexawol/state` |
| `alexawol-agent` | Subscribe | `alexawol/cmd` |
| `alexawol-agent` | Publish | `alexawol/state` |

O Lambda precisa assinar `alexawol/state` porque é assim que ele descobre se o PC está ligado
e qual o volume atual, na hora do `ReportState`.

Guarde as duas senhas — você vai precisar delas no `config.toml` do agente e nas variáveis de
ambiente do Lambda.

## Gerar o segredo HMAC

Os comandos são assinados, além de trafegarem por TLS autenticado. Gere um segredo e use o
**mesmo valor** nos dois lados:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Isso protege contra o cenário em que o broker é comprometido ou uma credencial vaza: sem o
segredo, ninguém consegue forjar um "desligar".

## Próximo passo

[setup-agent.md](setup-agent.md)
