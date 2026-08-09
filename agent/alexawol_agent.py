#!/usr/bin/env python3
"""Agente AlexaWOL — escuta comandos MQTT e os executa no PC.

Só precisa estar rodando quando o PC está ligado: "ligar" nunca passa por aqui, porque quem
transmite o magic packet é a própria Echo.

Uso:
    python alexawol_agent.py [caminho/para/config.toml]
"""

from __future__ import annotations

import json
import logging
import ssl
import sys
import threading
import time
import tomllib
from pathlib import Path

import paho.mqtt.client as mqtt

# `shared/` vive na raiz do repositório, um nível acima de agent/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.protocol import Rejected, prune_nonces, verify_command  # noqa: E402

import config_location  # noqa: E402
from actions import media, power, volume  # noqa: E402

log = logging.getLogger("alexawol")

STATE_REFRESH_SECONDS = 30


class Agent:
    def __init__(self, config: dict):
        self.cfg = config
        self.secret = config["security"]["secret"]
        self.cmd_topic = config["mqtt"]["cmd_topic"]
        self.state_topic = config["mqtt"]["state_topic"]

        self._seen_nonces: set[str] = set()
        self._nonce_stamps: dict[str, float] = {}

        self.client = self._build_client()

    # -- MQTT ---------------------------------------------------------------

    def _build_client(self) -> mqtt.Client:
        mq = self.cfg["mqtt"]
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=mq.get("client_id", "alexawol-agent"),
        )
        client.username_pw_set(mq["username"], mq["password"])
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
        client.reconnect_delay_set(min_delay=1, max_delay=60)

        # Se o agente cair — queda de rede, desligamento, travamento — o broker publica isto
        # sozinho, e a Alexa passa a reportar o PC como indisponível sem precisar de polling.
        client.will_set(
            self.state_topic,
            json.dumps({"online": False, "ts": int(time.time())}),
            qos=1,
            retain=True,
        )

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        return client

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.error("falha ao conectar: %s", reason_code)
            return
        log.info("conectado ao broker; assinando %s", self.cmd_topic)
        client.subscribe(self.cmd_topic, qos=1)
        self.publish_state()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        log.warning("desconectado (%s); paho vai reconectar sozinho", reason_code)

    def _on_message(self, client, userdata, message):
        try:
            payload = verify_command(message.payload, self.secret, self._seen_nonces)
        except Rejected as exc:
            log.warning("comando recusado: %s", exc)
            return

        self._nonce_stamps[payload["nonce"]] = time.time()
        prune_nonces(self._seen_nonces, self._nonce_stamps)

        action = payload["action"]
        params = payload.get("params") or {}
        log.info("executando %s %s", action, params)
        try:
            self.dispatch(action, params)
        except Exception:
            log.exception("erro ao executar %s", action)
            return

        self.publish_state()

    # -- Ações --------------------------------------------------------------

    def dispatch(self, action: str, params: dict) -> None:
        pw = self.cfg.get("power", {})
        delay = int(pw.get("shutdown_delay", 20))
        force = bool(pw.get("force", False))

        if action == "set_volume":
            volume.set_volume(params["percent"])
        elif action == "adjust_volume":
            volume.adjust_volume(params["delta"])
        elif action == "set_mute":
            volume.set_mute(bool(params["muted"]))
        elif action == "shutdown":
            power.shutdown(int(params.get("delay", delay)), force)
        elif action == "restart":
            power.restart(int(params.get("delay", delay)), force)
        elif action == "suspend":
            # Publica o estado antes de dormir — depois de suspender não há mais thread viva
            # para avisar ninguém.
            self.publish_state(online=True, suspending=True)
            power.suspend()
        elif action == "abort":
            power.abort()
        elif action == "play_music":
            media.play_target(self.cfg.get("media", {}).get("target", ""))
        elif action == "media_next":
            media.next_track()
        elif action == "media_previous":
            media.previous_track()
        elif action == "media_restart":
            media.restart_track()
        elif action == "media_play":
            media.play()
        elif action == "media_pause":
            media.pause()
        elif action == "report":
            pass  # o publish_state do chamador já basta
        else:
            # verify_command já filtrou pela allowlist; isto é só uma rede de segurança.
            raise ValueError(f"ação não tratada: {action}")

    # -- Estado -------------------------------------------------------------

    def publish_state(self, online: bool = True, suspending: bool = False) -> None:
        try:
            state = {
                "online": online,
                "volume": volume.get_volume(),
                "muted": volume.get_mute(),
                "suspending": suspending,
                "ts": int(time.time()),
            }
        except Exception:
            log.exception("não consegui ler o estado do áudio")
            state = {"online": online, "ts": int(time.time())}

        self.client.publish(self.state_topic, json.dumps(state), qos=1, retain=True)

    def _state_loop(self) -> None:
        """Republica o estado periodicamente.

        O volume pode mudar por fora (teclado, mixer, outro app) e a Alexa lê o retained
        na hora do ReportState, então vale manter esse valor fresco.
        """
        volume.com_init()
        while True:
            time.sleep(STATE_REFRESH_SECONDS)
            if self.client.is_connected():
                self.publish_state()

    # -- Execução -----------------------------------------------------------

    def run(self) -> None:
        mq = self.cfg["mqtt"]
        # O COM precisa ser inicializado em cada thread que toca o Core Audio. Esta é a
        # thread que o paho usa para os callbacks quando rodamos loop_forever aqui.
        volume.com_init()

        threading.Thread(target=self._state_loop, daemon=True).start()

        log.info("conectando em %s:%s", mq["host"], mq["port"])
        self.client.connect(mq["host"], int(mq["port"]), keepalive=45)
        self.client.loop_forever(retry_first_connection=True)


def load_config(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(
            f"config não encontrado: {path}\n"
            f"Copie agent/config.example.toml para lá e preencha as credenciais.\n"
            f"Local recomendado: {config_location.default_path()}"
        )
    with path.open("rb") as fh:
        return tomllib.load(fh)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
    )
    config_path = config_location.resolve(sys.argv[1] if len(sys.argv) > 1 else None)

    # O arquivo guarda as duas credenciais e o segredo HMAC. Numa pasta sincronizada ele sai
    # da máquina sozinho, o que anula a proteção — avisa alto, mas não impede de rodar.
    synced = config_location.warning_if_synced(config_path)
    if synced:
        log.warning(synced)

    log.info("config: %s", config_path)
    Agent(load_config(config_path)).run()


if __name__ == "__main__":
    main()
