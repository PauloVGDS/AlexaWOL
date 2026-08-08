"""Blocos de montagem das mensagens do Smart Home API v3."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import config

PAYLOAD_VERSION = "3"


def message_id() -> str:
    return str(uuid.uuid4())


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.00Z")


def header(namespace: str, name: str, correlation_token: str | None = None) -> dict:
    head = {
        "namespace": namespace,
        "name": name,
        "payloadVersion": PAYLOAD_VERSION,
        "messageId": message_id(),
    }
    if correlation_token:
        head["correlationToken"] = correlation_token
    return head


def prop(namespace: str, name: str, value, uncertainty_ms: int = 500) -> dict:
    return {
        "namespace": namespace,
        "name": name,
        "value": value,
        "timeOfSample": timestamp(),
        "uncertaintyInMilliseconds": uncertainty_ms,
    }


def _correlation(directive: dict) -> str | None:
    return directive["directive"]["header"].get("correlationToken")


def _endpoint_id(directive: dict) -> str:
    return directive["directive"].get("endpoint", {}).get("endpointId", config.ENDPOINT_ID)


def response(directive: dict, properties: list[dict], name: str = "Response") -> dict:
    """Resposta síncrona de sucesso, com o contexto de estado que a Alexa vai memorizar."""
    return {
        "context": {"properties": properties},
        "event": {
            "header": header("Alexa", name, _correlation(directive)),
            "endpoint": {"endpointId": _endpoint_id(directive)},
            "payload": {},
        },
    }


def error_response(directive: dict, error_type: str, message: str) -> dict:
    return {
        "event": {
            "header": header("Alexa", "ErrorResponse", _correlation(directive)),
            "endpoint": {"endpointId": _endpoint_id(directive)},
            "payload": {"type": error_type, "message": message},
        }
    }
