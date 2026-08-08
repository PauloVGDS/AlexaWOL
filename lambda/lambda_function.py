"""Ponto de entrada da Smart Home Skill AlexaWOL.

Roteia as diretivas do Smart Home API v3 para os módulos de cada interface.
"""

from __future__ import annotations

import json
import logging

from alexa import auth, discovery, power, scene, speaker, state
from alexa.util import error_response

log = logging.getLogger()
log.setLevel(logging.INFO)


def _route(directive: dict) -> dict:
    header = directive["directive"]["header"]
    namespace = header["namespace"]
    name = header["name"]

    if namespace == "Alexa.Discovery" and name == "Discover":
        return discovery.handle(directive)

    if namespace == "Alexa.Authorization" and name == "AcceptGrant":
        return auth.handle_accept_grant(directive)

    if namespace == "Alexa" and name == "ReportState":
        return state.handle_report_state(directive)

    if namespace == "Alexa.PowerController":
        return power.handle(directive)

    if namespace == "Alexa.Speaker":
        return speaker.handle(directive)

    if namespace == "Alexa.SceneController":
        return scene.handle(directive)

    return error_response(
        directive, "INVALID_DIRECTIVE", f"diretiva não suportada: {namespace}.{name}"
    )


def lambda_handler(event, context):
    log.info("directive: %s", json.dumps(event))

    try:
        result = _route(event)
    except Exception as exc:
        log.exception("erro não tratado")
        try:
            result = error_response(event, "INTERNAL_ERROR", str(exc))
        except Exception:
            # O evento nem parece uma diretiva Alexa — não há como montar uma resposta
            # correlacionada, então deixamos o erro subir para o CloudWatch.
            raise

    log.info("response: %s", json.dumps(result))
    return result
