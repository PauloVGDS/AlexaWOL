"""Leitura de estado do PC e montagem das propriedades que a Alexa espera."""

from __future__ import annotations

import logging

from alexa.util import prop, response
from bridge import mqtt_client

log = logging.getLogger()


def properties(state: dict | None) -> list[dict]:
    """Converte o estado publicado pelo agente em propriedades do Smart Home API.

    `state` é None quando não há mensagem retida — ou seja, o agente nunca conectou.
    """
    online = bool(state and state.get("online"))

    props = [
        prop("Alexa.PowerController", "powerState", "ON" if online else "OFF"),
        # Sempre OK, de propósito. Se reportássemos UNREACHABLE com o PC desligado, a Alexa
        # trataria o dispositivo como fora do ar e poderia recusar justamente o "ligue o
        # computador", que é o comando que precisa funcionar nesse estado.
        prop("Alexa.EndpointHealth", "connectivity", {"value": "OK"}),
    ]

    if online and state is not None:
        if "volume" in state:
            props.append(prop("Alexa.Speaker", "volume", int(state["volume"])))
        if "muted" in state:
            props.append(prop("Alexa.Speaker", "muted", bool(state["muted"])))

    return props


def current_properties() -> list[dict]:
    try:
        state = mqtt_client.read_state()
    except Exception:
        log.exception("falha ao ler o estado no broker; assumindo PC desligado")
        state = None
    return properties(state)


def handle_report_state(directive: dict) -> dict:
    return response(directive, current_properties(), name="StateReport")
