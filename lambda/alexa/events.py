"""Envio de eventos ao Alexa event gateway."""

from __future__ import annotations

import json
import logging
import urllib.request

import config
from alexa import auth
from alexa.util import header

log = logging.getLogger()


def post_event(event: dict) -> None:
    body = json.dumps(event).encode("utf-8")
    request = urllib.request.Request(
        config.EVENT_GATEWAY,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as resp:
        log.info("event gateway respondeu %s", resp.status)


def send_wake_up(endpoint_id: str, correlation_token: str | None) -> None:
    """Pede à Alexa que uma Echo da rede local transmita o magic packet.

    Este é o coração do projeto. A Echo já sabe o MAC (veio na resposta de Discovery); aqui
    apenas disparamos a ação. Nenhum pacote sai da nossa infraestrutura para a rede do
    usuário.
    """
    post_event(
        {
            "event": {
                "header": header(
                    "Alexa.WakeOnLANController", "WakeUp", correlation_token
                ),
                "endpoint": {
                    "scope": {"type": "BearerToken", "token": auth.get_access_token()},
                    "endpointId": endpoint_id,
                },
                "payload": {},
            }
        }
    )
