"""Alexa.PlaybackController: avançar e voltar faixa.

Traduz as operações da Alexa nas teclas de mídia do Windows, que qualquer player respeita —
Spotify, YouTube, VLC — sem precisar integrar com nenhum deles.

Só `Next` e `Previous` são declarados. `Play` e `Pause` ficaram de fora de propósito: o
Windows tem uma única tecla de alternância, então mapear as duas operações nela faria
"pausar" retomar a música quando ela já estivesse pausada. Ver a nota em
`agent/actions/media.py`.
"""

from __future__ import annotations

import logging

from alexa.util import error_response, response
from bridge import mqtt_client

log = logging.getLogger()

_ACTION_BY_OPERATION = {
    "Next": "media_next",
    "Previous": "media_previous",
}


def handle(directive: dict) -> dict:
    operation = directive["directive"]["header"]["name"]
    action = _ACTION_BY_OPERATION.get(operation)
    if action is None:
        return error_response(
            directive,
            "INVALID_DIRECTIVE",
            f"PlaybackController.{operation} não é suportada",
        )

    try:
        mqtt_client.publish_command(action)
    except Exception as exc:
        log.exception("falha ao publicar %s", action)
        return error_response(
            directive, "ENDPOINT_UNREACHABLE", f"não consegui falar com o PC: {exc}"
        )

    # Sem contexto de estado: não implementamos o Alexa.PlaybackStateReporter, porque
    # descobrir se está tocando exigiria o SMTC do Windows. A Alexa aceita a resposta vazia.
    return response(directive, [])
