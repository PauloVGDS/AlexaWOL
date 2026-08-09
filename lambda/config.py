"""Configuração do Lambda, toda por variável de ambiente.

Segredos ficam nas variáveis de ambiente da função (criptografadas em repouso). A única
coisa guardada no SSM é o refresh token, porque ele é escrito em tempo de execução, quando
chega o AcceptGrant.
"""

import os

# -- Endpoint exposto para a Alexa ----------------------------------------------------
ENDPOINT_ID = os.environ.get("ENDPOINT_ID", "alexawol-pc")
FRIENDLY_NAME = os.environ.get("FRIENDLY_NAME", "Computador")
# MAC do PC, com hífen: "00-11-22-33-44-55". É o que a Echo usa no magic packet.
PC_MAC = os.environ["PC_MAC"]

# Segundo endpoint, exposto como cena. PowerController só tem ligar/desligar, então
# "suspender" precisa de um dispositivo próprio para não colidir com "desligar".
SUSPEND_ENDPOINT_ID = os.environ.get("SUSPEND_ENDPOINT_ID", "alexawol-pc-suspend")
SUSPEND_FRIENDLY_NAME = os.environ.get("SUSPEND_FRIENDLY_NAME", "Suspensão do computador")

# Terceira cena: manda o PC abrir a mídia configurada no agente. O que tocar não é decidido
# aqui nem trafega pela rede — mora no config.toml do agente.
MUSIC_ENDPOINT_ID = os.environ.get("MUSIC_ENDPOINT_ID", "alexawol-pc-music")
MUSIC_FRIENDLY_NAME = os.environ.get("MUSIC_FRIENDLY_NAME", "Música do computador")

# -- Alexa event gateway ---------------------------------------------------------------
# pt-BR é servido por US East (N. Virginia), cujo gateway é o da América do Norte.
# Europa/Índia: https://api.eu.amazonalexa.com/v3/events
# Extremo Oriente/Austrália: https://api.fe.amazonalexa.com/v3/events
EVENT_GATEWAY = os.environ.get("EVENT_GATEWAY", "https://api.amazonalexa.com/v3/events")

# -- Login with Amazon ------------------------------------------------------------------
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"

# ⚠️ ARMADILHA: estas NÃO são as credenciais do Security Profile usado no account linking.
# São as de **Alexa Skill Messaging**, em Build > Permissions no console da skill, reveladas
# pelo botão SHOW depois de ligar o toggle "Send Alexa Events".
#
# As duas têm exatamente o mesmo formato (`amzn1.application-oa2-client.…`), então trocar uma
# pela outra não dá erro nenhum na configuração — a falha só aparece muito depois, e só no
# "ligar o computador", porque é o único caminho que troca o código do AcceptGrant por tokens.
#
# Papéis distintos: o Security Profile autentica o USUÁRIO no vínculo da conta; estas aqui
# autenticam a SKILL perante o event gateway.
LWA_CLIENT_ID = os.environ["LWA_CLIENT_ID"]
LWA_CLIENT_SECRET = os.environ["LWA_CLIENT_SECRET"]
SSM_REFRESH_TOKEN_PARAM = os.environ.get("SSM_REFRESH_TOKEN_PARAM", "/alexawol/refresh_token")

# -- Ponte MQTT --------------------------------------------------------------------------
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ.get("MQTT_PORT", "8883"))
MQTT_USERNAME = os.environ["MQTT_USERNAME"]
MQTT_PASSWORD = os.environ["MQTT_PASSWORD"]
MQTT_CMD_TOPIC = os.environ.get("MQTT_CMD_TOPIC", "alexawol/cmd")
MQTT_STATE_TOPIC = os.environ.get("MQTT_STATE_TOPIC", "alexawol/state")

# Segredo HMAC, idêntico ao do config.toml do agente.
HMAC_SECRET = os.environ["HMAC_SECRET"]

# Quanto esperar pela mensagem retida de estado antes de assumir que o PC está desligado.
STATE_READ_TIMEOUT = float(os.environ.get("STATE_READ_TIMEOUT", "3"))
