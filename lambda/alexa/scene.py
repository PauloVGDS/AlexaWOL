"""SceneController — as ações do PC que não cabem em ligar/desligar.

PowerController só tem dois estados e o "desligar" já ocupa um deles. Cada ação extra
(suspender, tocar música) vira uma cena com endpoint próprio. Para acrescentar outra, some
uma entrada em `_ACTION_BY_ENDPOINT`, o endpoint correspondente em `discovery.py`, a ação na
allowlist de `shared/protocol.py` e o tratamento no `dispatch()` do agente.
"""

from __future__ import annotations

import logging

import config
from alexa.util import error_response, header, timestamp
from bridge import mqtt_client

log = logging.getLogger()

_ACTION_BY_ENDPOINT = {
    config.SUSPEND_ENDPOINT_ID: "suspend",
    config.MUSIC_ENDPOINT_ID: "play_music",
}


def handle(directive: dict) -> dict:
    head = directive["directive"]["header"]
    if head["name"] != "Activate":
        return error_response(
            directive, "INVALID_DIRECTIVE", f"SceneController.{head['name']}"
        )

    endpoint_id = directive["directive"]["endpoint"]["endpointId"]
    action = _ACTION_BY_ENDPOINT.get(endpoint_id)
    if action is None:
        return error_response(
            directive, "NO_SUCH_ENDPOINT", f"cena desconhecida: {endpoint_id}"
        )

    try:
        mqtt_client.publish_command(action)
    except Exception as exc:
        log.exception("falha ao publicar %s", action)
        return error_response(
            directive, "ENDPOINT_UNREACHABLE", f"não consegui falar com o PC: {exc}"
        )

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
