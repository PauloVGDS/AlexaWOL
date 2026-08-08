"""PowerController: ligar (Wake-on-LAN pela Echo) e desligar (MQTT → agente)."""

from __future__ import annotations

import logging

import config
from alexa import events
from alexa.util import error_response, prop, response
from bridge import mqtt_client

log = logging.getLogger()


def handle_turn_on(directive: dict) -> dict:
    """Liga o PC.

    Não publicamos nada no MQTT — o PC está desligado, não há ninguém escutando. Em vez
    disso pedimos à Alexa que uma Echo da rede local transmita o magic packet.

    A documentação descreve um fluxo com DeferredResponse antes do evento WakeUp. Na
    prática o evento seguido da resposta síncrona funciona e é bem mais simples, porque o
    Lambda congela assim que retorna — não daria para enviar o evento "depois".
    """
    header = directive["directive"]["header"]
    endpoint_id = directive["directive"].get("endpoint", {}).get(
        "endpointId", config.ENDPOINT_ID
    )

    try:
        events.send_wake_up(endpoint_id, header.get("correlationToken"))
    except Exception as exc:
        log.exception("falha ao enviar o evento WakeUp")
        return error_response(
            directive,
            "INTERNAL_ERROR",
            f"não consegui pedir o Wake-on-LAN à Alexa: {exc}",
        )

    return response(
        directive,
        [
            prop("Alexa.PowerController", "powerState", "ON"),
            prop("Alexa.EndpointHealth", "connectivity", {"value": "OK"}),
        ],
    )


def handle_turn_off(directive: dict) -> dict:
    """Desliga o PC de verdade (S5), com a janela de cancelamento do agente."""
    try:
        mqtt_client.publish_command("shutdown")
    except Exception as exc:
        log.exception("falha ao publicar o comando de desligar")
        return error_response(
            directive, "ENDPOINT_UNREACHABLE", f"não consegui falar com o PC: {exc}"
        )

    return response(
        directive,
        [
            prop("Alexa.PowerController", "powerState", "OFF"),
            prop("Alexa.EndpointHealth", "connectivity", {"value": "OK"}),
        ],
    )


def handle(directive: dict) -> dict:
    name = directive["directive"]["header"]["name"]
    if name == "TurnOn":
        return handle_turn_on(directive)
    if name == "TurnOff":
        return handle_turn_off(directive)
    return error_response(directive, "INVALID_DIRECTIVE", f"PowerController.{name}")
