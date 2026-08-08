#!/usr/bin/env python3
"""Publica um comando assinado no broker, para testar o agente sem envolver a Alexa.

É a etapa 2 da verificação: com isto você valida volume, mudo, suspender e desligar antes
de existir qualquer Lambda.

    python send_cmd.py set_volume --percent 30
    python send_cmd.py set_mute --muted true
    python send_cmd.py suspend
    python send_cmd.py shutdown --delay 30
    python send_cmd.py abort

Também serve para o teste negativo de segurança:

    python send_cmd.py set_volume --percent 30 --tamper     # deve ser recusado
    python send_cmd.py set_volume --percent 30 --stale      # deve ser recusado
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import time
import tomllib
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.protocol import build_command, sign  # noqa: E402


def load_config() -> dict:
    path = Path(__file__).resolve().parents[1] / "agent" / "config.toml"
    if not path.exists():
        raise SystemExit(f"config não encontrado: {path}")
    with path.open("rb") as fh:
        return tomllib.load(fh)


def build_params(args: argparse.Namespace) -> dict:
    if args.action == "set_volume":
        return {"percent": args.percent}
    if args.action == "adjust_volume":
        return {"delta": args.delta}
    if args.action == "set_mute":
        return {"muted": args.muted == "true"}
    if args.action in ("shutdown", "restart"):
        return {"delay": args.delay}
    return {}


def corrupt(message: str, tamper: bool, stale: bool, secret: str) -> str:
    """Produz uma mensagem que o agente DEVE recusar."""
    envelope = json.loads(message)
    if tamper:
        envelope["payload"]["params"]["percent"] = 100  # muda o payload, mantém a assinatura
    if stale:
        envelope["payload"]["ts"] = int(time.time()) - 3600
        envelope["sig"] = sign(envelope["payload"], secret)  # assinatura válida, tempo velho
    return json.dumps(envelope)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publica um comando assinado no broker.")
    parser.add_argument(
        "action",
        choices=[
            "set_volume",
            "adjust_volume",
            "set_mute",
            "shutdown",
            "restart",
            "suspend",
            "abort",
            "report",
        ],
    )
    parser.add_argument("--percent", type=int, default=30)
    parser.add_argument("--delta", type=int, default=10)
    parser.add_argument("--muted", choices=["true", "false"], default="true")
    parser.add_argument("--delay", type=int, default=20)
    parser.add_argument("--tamper", action="store_true", help="quebra a assinatura de propósito")
    parser.add_argument("--stale", action="store_true", help="usa timestamp de uma hora atrás")
    args = parser.parse_args()

    cfg = load_config()
    mq = cfg["mqtt"]
    secret = cfg["security"]["secret"]

    message = build_command(args.action, secret, build_params(args))
    if args.tamper or args.stale:
        message = corrupt(message, args.tamper, args.stale, secret)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="alexawol-testcli")
    client.username_pw_set(mq["username"], mq["password"])
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    client.connect(mq["host"], int(mq["port"]), keepalive=30)
    client.loop_start()
    info = client.publish(mq["cmd_topic"], message, qos=1)
    info.wait_for_publish(timeout=10)
    client.loop_stop()
    client.disconnect()

    print(f"publicado em {mq['cmd_topic']}: {message}")
    if args.tamper or args.stale:
        print(">>> esta mensagem DEVE ser recusada pelo agente. Confira o log dele.")


if __name__ == "__main__":
    main()
