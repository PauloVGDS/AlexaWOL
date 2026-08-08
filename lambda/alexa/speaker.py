"""Alexa.Speaker: volume absoluto, ajuste relativo e mudo."""

from __future__ import annotations

import logging

from alexa.util import error_response, prop, response
from bridge import mqtt_client

log = logging.getLogger()


def _current_volume() -> int:
    """Último volume conhecido, vindo da mensagem retida do agente."""
    state = mqtt_client.read_state()
    if state and "volume" in state:
        return int(state["volume"])
    return 0


def _volume_response(directive: dict, volume: int, muted: bool | None = None) -> dict:
    """Responde com o valor que esperamos que o PC tenha aplicado.

    É otimista de propósito: esperar o agente confirmar custaria uma ida e volta que não
    cabe nos 8 segundos da Alexa. O agente republica o estado real logo em seguida, então
    um eventual desencontro se corrige sozinho no próximo ReportState.
    """
    props = [prop("Alexa.Speaker", "volume", volume)]
    if muted is not None:
        props.append(prop("Alexa.Speaker", "muted", muted))
    return response(directive, props)


def handle(directive: dict) -> dict:
    name = directive["directive"]["header"]["name"]
    payload = directive["directive"]["payload"]

    try:
        if name == "SetVolume":
            volume = max(0, min(100, int(payload["volume"])))
            mqtt_client.publish_command("set_volume", {"percent": volume})
            return _volume_response(directive, volume)

        if name == "AdjustVolume":
            delta = int(payload["volume"])
            target = max(0, min(100, _current_volume() + delta))
            mqtt_client.publish_command("adjust_volume", {"delta": delta})
            return _volume_response(directive, target)

        if name == "SetMute":
            muted = bool(payload["mute"])
            mqtt_client.publish_command("set_mute", {"muted": muted})
            return _volume_response(directive, _current_volume(), muted)

    except Exception as exc:
        log.exception("falha em Speaker.%s", name)
        return error_response(
            directive, "ENDPOINT_UNREACHABLE", f"não consegui falar com o PC: {exc}"
        )

    return error_response(directive, "INVALID_DIRECTIVE", f"Speaker.{name}")
