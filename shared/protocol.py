"""Formato e assinatura das mensagens trocadas entre o Lambda e o agente do PC.

Usado pelos dois lados. O `build.ps1` do Lambda copia este arquivo para dentro do zip de
deploy; o agente o importa a partir da raiz do repositório.

A assinatura é defesa em profundidade — o HiveMQ já provê TLS, credenciais e ACL por tópico.
Ela cobre o caso de broker comprometido ou credencial vazada.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time

# Toda ação executável precisa estar aqui. O agente nunca interpreta string arbitraria
# vinda da rede.
ACTIONS = frozenset(
    {
        "set_volume",  # params: {"percent": 0-100}
        "adjust_volume",  # params: {"delta": -100..100}
        "set_mute",  # params: {"muted": bool}
        "shutdown",  # params: {"delay": segundos}
        "suspend",
        "restart",  # params: {"delay": segundos}
        "abort",  # cancela shutdown/restart agendado
        "report",  # pede ao agente que republique o estado
        # Sem params de propósito: o QUE tocar vem do config local do agente, nunca da
        # rede. Se a mídia viesse no payload, quem tivesse o segredo HMAC faria o PC abrir
        # qualquer coisa.
        "play_music",
        "media_next",  # tecla de mídia "próxima faixa"
        "media_previous",  # tecla de mídia "faixa anterior"
    }
)

# Janela de aceitação do timestamp. Precisa ser folgada o bastante para o cold start do
# Lambda e apertada o bastante para que um comando capturado não sirva depois.
MAX_AGE_SECONDS = 30


def canonical(payload: dict) -> bytes:
    """Serialização determinística — os dois lados precisam produzir os mesmos bytes."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(payload: dict, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), canonical(payload), hashlib.sha256).hexdigest()


def build_command(action: str, secret: str, params: dict | None = None) -> str:
    """Monta uma mensagem de comando assinada, pronta para publicar."""
    if action not in ACTIONS:
        raise ValueError(f"ação desconhecida: {action}")

    payload = {
        "action": action,
        "params": params or {},
        "ts": int(time.time()),
        "nonce": secrets.token_hex(8),
    }
    return json.dumps({"payload": payload, "sig": sign(payload, secret)})


class Rejected(Exception):
    """Mensagem recusada. A mensagem da exceção diz o motivo, para log."""


def verify_command(raw: bytes | str, secret: str, seen_nonces: set[str]) -> dict:
    """Valida uma mensagem recebida e devolve o payload.

    Levanta `Rejected` em qualquer falha. `seen_nonces` é mutado com o nonce aceito.
    """
    try:
        envelope = json.loads(raw)
        payload = envelope["payload"]
        sig = envelope["sig"]
        action = payload["action"]
        nonce = payload["nonce"]
        ts = int(payload["ts"])
    except (ValueError, KeyError, TypeError) as exc:
        raise Rejected(f"mensagem malformada: {exc}") from exc

    if not hmac.compare_digest(sig, sign(payload, secret)):
        raise Rejected("assinatura inválida")

    age = time.time() - ts
    if abs(age) > MAX_AGE_SECONDS:
        # Cobre também o caso de mensagem retida/reentregue por um broker depois de horas.
        raise Rejected(f"timestamp fora da janela ({age:.0f}s)")

    if nonce in seen_nonces:
        raise Rejected("nonce repetido (replay)")

    if action not in ACTIONS:
        raise Rejected(f"ação fora da allowlist: {action!r}")

    seen_nonces.add(nonce)
    return payload


def prune_nonces(seen_nonces: set[str], stamps: dict[str, float]) -> None:
    """Descarta nonces velhos o bastante para que o timestamp já os rejeitasse sozinho."""
    cutoff = time.time() - (MAX_AGE_SECONDS * 2)
    for nonce in [n for n, t in stamps.items() if t < cutoff]:
        stamps.pop(nonce, None)
        seen_nonces.discard(nonce)
