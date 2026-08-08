"""Resposta de Discovery — descreve o PC como dispositivos para a Alexa.

São dois endpoints: o computador em si (ligar/desligar/volume) e uma cena separada para
suspender, porque PowerController não comporta três estados.
"""

from __future__ import annotations

import config
from alexa.util import header


def _capability(interface: str, supported: list[str] | None = None, **extra) -> dict:
    cap = {"type": "AlexaInterface", "interface": interface, "version": "3"}
    if supported is not None:
        cap["properties"] = {
            "supported": [{"name": name} for name in supported],
            "proactivelyReported": False,
            "retrievable": True,
        }
    cap.update(extra)
    return cap


def _computer_endpoint() -> dict:
    return {
        "endpointId": config.ENDPOINT_ID,
        "manufacturerName": "AlexaWOL",
        "description": "PC controlado pelo AlexaWOL",
        "friendlyName": config.FRIENDLY_NAME,
        # COMPUTER faz a Alexa entender "ligue o computador" sem precisar de rotina.
        "displayCategories": ["COMPUTER"],
        "cookie": {},
        "capabilities": [
            _capability("Alexa"),
            _capability("Alexa.PowerController", ["powerState"]),
            # É esta capability que faz a mágica: a Alexa lê o MAC daqui e manda uma Echo
            # da rede local transmitir o magic packet. Nenhum servidor nosso participa.
            _capability(
                "Alexa.WakeOnLANController",
                configuration={"MACAddresses": [config.PC_MAC]},
            ),
            _capability("Alexa.Speaker", ["volume", "muted"]),
            _capability("Alexa.EndpointHealth", ["connectivity"]),
        ],
    }


def _suspend_endpoint() -> dict:
    return {
        "endpointId": config.SUSPEND_ENDPOINT_ID,
        "manufacturerName": "AlexaWOL",
        "description": "Suspende o PC (AlexaWOL)",
        "friendlyName": config.SUSPEND_FRIENDLY_NAME,
        "displayCategories": ["SCENE_TRIGGER"],
        "cookie": {},
        "capabilities": [
            _capability("Alexa"),
            # supportsDeactivation=False: "desativar" uma suspensão não significa nada —
            # para trazer o PC de volta existe o "ligue o computador".
            _capability("Alexa.SceneController", supportsDeactivation=False),
        ],
    }


def handle(directive: dict) -> dict:
    return {
        "event": {
            "header": header("Alexa.Discovery", "Discover.Response"),
            "payload": {"endpoints": [_computer_endpoint(), _suspend_endpoint()]},
        }
    }
