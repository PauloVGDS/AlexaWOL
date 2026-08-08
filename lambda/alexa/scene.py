"""SceneController — expõe "suspender" como um segundo dispositivo.

PowerController só tem ligar e desligar, e o usuário quer suspender e desligar como
comandos distintos. Uma cena resolve isso sem ambiguidade: "Alexa, ativar suspensão do
computador". Se quiser uma frase mais curta, crie uma Rotina no app apontando para ela.
"""

from __future__ import annotations

import logging

from alexa.util import error_response, header, timestamp
from bridge import mqtt_client

log = logging.getLogger()


def handle(directive: dict) -> dict:
    name = directive["directive"]["header"]["name"]
    if name != "Activate":
        return error_response(directive, "INVALID_DIRECTIVE", f"SceneController.{name}")

    try:
        mqtt_client.publish_command("suspend")
    except Exception as exc:
        log.exception("falha ao publicar o comando de suspender")
        return error_response(
            directive, "ENDPOINT_UNREACHABLE", f"não consegui falar com o PC: {exc}"
        )

    head = directive["directive"]["header"]
    endpoint_id = directive["directive"]["endpoint"]["endpointId"]
    return {
        "context": {},
        "event": {
            "header": header(
                "Alexa.SceneController",
                "ActivationStarted",
                head.get("correlationToken"),
            ),
            "endpoint": {"endpointId": endpoint_id},
            "payload": {
                "cause": {"type": "VOICE_INTERACTION"},
                "timestamp": timestamp(),
            },
        },
    }
