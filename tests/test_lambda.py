#!/usr/bin/env python3
"""Exercita o handler do Lambda sem AWS, sem broker e sem Alexa.

É a etapa 3 da verificação: confere que cada diretiva produz um JSON válido do Smart Home
API v3 antes de existir qualquer infraestrutura.

    python tests/test_lambda.py
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "lambda"))

# -- Ambiente falso -----------------------------------------------------------------------
os.environ.update(
    {
        "PC_MAC": "00-11-22-33-44-55",
        "FRIENDLY_NAME": "Computador",
        "LWA_CLIENT_ID": "fake-client-id",
        "LWA_CLIENT_SECRET": "fake-client-secret",
        "MQTT_HOST": "fake.hivemq.cloud",
        "MQTT_USERNAME": "fake-user",
        "MQTT_PASSWORD": "fake-pass",
        "HMAC_SECRET": "segredo-de-teste",
    }
)

# boto3 só existe no runtime da AWS; aqui basta um esqueleto que não é chamado.
if "boto3" not in sys.modules:
    boto3_stub = types.ModuleType("boto3")
    boto3_stub.client = lambda *a, **k: None
    sys.modules["boto3"] = boto3_stub

import lambda_function  # noqa: E402
from bridge import mqtt_client  # noqa: E402

# -- Dublês da ponte MQTT e do event gateway ----------------------------------------------
published: list[tuple[str, dict]] = []
wake_ups: list[tuple[str, str]] = []
FAKE_STATE = {"online": True, "volume": 45, "muted": False}

mqtt_client.publish_command = lambda action, params=None: published.append((action, params or {}))
mqtt_client.read_state = lambda timeout=None: FAKE_STATE

from alexa import events, power, speaker, state  # noqa: E402

power.mqtt_client = mqtt_client
speaker.mqtt_client = mqtt_client
state.mqtt_client = mqtt_client
events.send_wake_up = lambda endpoint_id, token: wake_ups.append((endpoint_id, token))
power.events = events


# -- Helpers ------------------------------------------------------------------------------
def directive(namespace: str, name: str, payload: dict | None = None, endpoint: str | None = None):
    header = {
        "namespace": namespace,
        "name": name,
        "payloadVersion": "3",
        "messageId": "msg-1",
    }
    if namespace != "Alexa.Discovery":
        header["correlationToken"] = "corr-1"
    body = {"header": header, "payload": payload or {}}
    if endpoint:
        body["endpoint"] = {"endpointId": endpoint, "scope": {"type": "BearerToken", "token": "t"}}
    return {"directive": body}


failures = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global failures
    if condition:
        print(f"  OK       {label}")
    else:
        failures += 1
        print(f"  FALHOU   {label} {detail}")


def prop_value(result: dict, namespace: str, name: str):
    for item in result.get("context", {}).get("properties", []):
        if item["namespace"] == namespace and item["name"] == name:
            return item["value"]
    return None


# -- Testes -------------------------------------------------------------------------------
print("Discovery:")
res = lambda_function.lambda_handler(directive("Alexa.Discovery", "Discover"), None)
endpoints = res["event"]["payload"]["endpoints"]
check("devolve 3 endpoints", len(endpoints) == 3, f"({len(endpoints)})")

pc = endpoints[0]
interfaces = {c["interface"]: c for c in pc["capabilities"]}
check("categoria COMPUTER", pc["displayCategories"] == ["COMPUTER"])
check("tem PowerController", "Alexa.PowerController" in interfaces)
check("tem Speaker", "Alexa.Speaker" in interfaces)
check("tem WakeOnLANController", "Alexa.WakeOnLANController" in interfaces)
mac = interfaces.get("Alexa.WakeOnLANController", {}).get("configuration", {}).get("MACAddresses")
check("MAC no formato com hifen", mac == ["00-11-22-33-44-55"], f"({mac})")
for index, label in ((1, "suspender"), (2, "musica")):
    check(
        f"endpoint de {label} e cena",
        "Alexa.SceneController" in {c["interface"] for c in endpoints[index]["capabilities"]},
    )

print("TurnOn (Wake-on-LAN):")
wake_ups.clear()
published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.PowerController", "TurnOn", endpoint="alexawol-pc"), None
)
check("enviou o evento WakeUp", len(wake_ups) == 1, f"({wake_ups})")
check("NAO publicou no MQTT", published == [], f"({published})")
check("responde powerState ON", prop_value(res, "Alexa.PowerController", "powerState") == "ON")
check("correlationToken preservado", res["event"]["header"].get("correlationToken") == "corr-1")

print("TurnOff:")
wake_ups.clear()
published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.PowerController", "TurnOff", endpoint="alexawol-pc"), None
)
check("publicou shutdown", published == [("shutdown", {})], f"({published})")
check("responde powerState OFF", prop_value(res, "Alexa.PowerController", "powerState") == "OFF")

print("Speaker:")
published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.Speaker", "SetVolume", {"volume": 30}, endpoint="alexawol-pc"), None
)
check("publicou set_volume 30", published == [("set_volume", {"percent": 30})], f"({published})")
check("responde volume 30", prop_value(res, "Alexa.Speaker", "volume") == 30)

published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.Speaker", "AdjustVolume", {"volume": -15}, endpoint="alexawol-pc"), None
)
check("publicou adjust_volume -15", published == [("adjust_volume", {"delta": -15})], f"({published})")
check("responde 45-15=30", prop_value(res, "Alexa.Speaker", "volume") == 30)

published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.Speaker", "SetMute", {"mute": True}, endpoint="alexawol-pc"), None
)
check("publicou set_mute", published == [("set_mute", {"muted": True})], f"({published})")
check("responde muted True", prop_value(res, "Alexa.Speaker", "muted") is True)

print("Cenas:")
# Cada cena precisa publicar a SUA ação. Enquanto existia só uma, o handler publicava
# "suspend" incondicionalmente e passava — ativar a música suspenderia o PC.
published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.SceneController", "Activate", endpoint="alexawol-pc-suspend"), None
)
check("suspender publica suspend", published == [("suspend", {})], f"({published})")
check("responde ActivationStarted", res["event"]["header"]["name"] == "ActivationStarted")

published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.SceneController", "Activate", endpoint="alexawol-pc-music"), None
)
check("musica publica play_music", published == [("play_music", {})], f"({published})")
check("responde ActivationStarted", res["event"]["header"]["name"] == "ActivationStarted")
check(
    "endpointId ecoado corretamente",
    res["event"]["endpoint"]["endpointId"] == "alexawol-pc-music",
)

published.clear()
res = lambda_function.lambda_handler(
    directive("Alexa.SceneController", "Activate", endpoint="cena-inexistente"), None
)
check("cena desconhecida nao publica nada", published == [], f"({published})")
check(
    "cena desconhecida devolve NO_SUCH_ENDPOINT",
    res["event"]["payload"]["type"] == "NO_SUCH_ENDPOINT",
)

print("ReportState:")
res = lambda_function.lambda_handler(directive("Alexa", "ReportState", endpoint="alexawol-pc"), None)
check("nome StateReport", res["event"]["header"]["name"] == "StateReport")
check("powerState ON quando online", prop_value(res, "Alexa.PowerController", "powerState") == "ON")
check("reporta volume 45", prop_value(res, "Alexa.Speaker", "volume") == 45)

original = mqtt_client.read_state
mqtt_client.read_state = lambda timeout=None: None
state.mqtt_client = mqtt_client
res = lambda_function.lambda_handler(directive("Alexa", "ReportState", endpoint="alexawol-pc"), None)
check("powerState OFF sem retained", prop_value(res, "Alexa.PowerController", "powerState") == "OFF")
check(
    "conectividade segue OK com PC desligado",
    prop_value(res, "Alexa.EndpointHealth", "connectivity") == {"value": "OK"},
)
mqtt_client.read_state = original
state.mqtt_client = mqtt_client

print("Diretiva desconhecida:")
res = lambda_function.lambda_handler(directive("Alexa.ThermostatController", "SetTargetTemperature"), None)
check("devolve ErrorResponse", res["event"]["header"]["name"] == "ErrorResponse")
check("tipo INVALID_DIRECTIVE", res["event"]["payload"]["type"] == "INVALID_DIRECTIVE")

print()
if failures:
    print(f"{failures} verificação(ões) falharam.")
    sys.exit(1)
print("Todas as verificações passaram.")
