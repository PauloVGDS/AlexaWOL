"""Account linking: troca do grant do AcceptGrant e renovação do access token.

O refresh token é a única coisa que precisa sobreviver entre invocações, então mora no SSM
Parameter Store como SecureString — de graça, um parâmetro só, sem tabela para administrar.
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

import boto3
import config
from alexa.util import header

log = logging.getLogger()

_ssm = boto3.client("ssm")


def _post_token_request(data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        config.LWA_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as resp:
        return json.loads(resp.read())


def _store_refresh_token(token: str) -> None:
    _ssm.put_parameter(
        Name=config.SSM_REFRESH_TOKEN_PARAM,
        Value=token,
        Type="SecureString",
        Overwrite=True,
    )


def _load_refresh_token() -> str:
    param = _ssm.get_parameter(Name=config.SSM_REFRESH_TOKEN_PARAM, WithDecryption=True)
    return param["Parameter"]["Value"]


def handle_accept_grant(directive: dict) -> dict:
    """Troca o código de autorização por access + refresh token e guarda o refresh.

    A Alexa manda este directive uma vez, quando você habilita a skill no app. Sem ele não
    há como enviar eventos ao gateway — e, portanto, não há como acordar o PC.
    """
    payload = directive["directive"]["payload"]
    code = payload["grant"]["code"]

    try:
        tokens = _post_token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": config.LWA_CLIENT_ID,
                "client_secret": config.LWA_CLIENT_SECRET,
            }
        )
        _store_refresh_token(tokens["refresh_token"])
    except Exception as exc:
        log.exception("AcceptGrant falhou")
        return {
            "event": {
                "header": header("Alexa.Authorization", "ErrorResponse"),
                "payload": {"type": "ACCEPT_GRANT_FAILED", "message": str(exc)},
            }
        }

    log.info("AcceptGrant concluído; refresh token guardado no SSM")
    return {
        "event": {
            "header": header("Alexa.Authorization", "AcceptGrant.Response"),
            "payload": {},
        }
    }


def get_access_token() -> str:
    """Devolve um access token válido, renovando pelo refresh token guardado."""
    tokens = _post_token_request(
        {
            "grant_type": "refresh_token",
            "refresh_token": _load_refresh_token(),
            "client_id": config.LWA_CLIENT_ID,
            "client_secret": config.LWA_CLIENT_SECRET,
        }
    )
    # O LWA pode devolver um refresh token novo; se devolver, o antigo deixa de valer.
    if tokens.get("refresh_token"):
        _store_refresh_token(tokens["refresh_token"])
    return tokens["access_token"]
