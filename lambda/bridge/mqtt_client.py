"""Ponte MQTT do Lambda para o agente no PC.

O Lambda é efêmero, então cada invocação conecta, faz o que precisa e desconecta. O custo
é de uns 200-300 ms, bem dentro dos 8 segundos que a Alexa concede.
"""

from __future__ import annotations

import json
import logging
import ssl
import threading

import config
import paho.mqtt.client as mqtt
from shared.protocol import build_command

log = logging.getLogger()


def _client(client_id: str) -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    client.username_pw_set(config.MQTT_USERNAME, config.MQTT_PASSWORD)
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLSv1_2)
    return client


def publish_command(action: str, params: dict | None = None) -> None:
    """Publica um comando assinado. Não espera confirmação de execução.

    Fire-and-forget é obrigatório aqui: o Lambda congela ao retornar, e esperar o PC
    confirmar um desligamento estouraria o limite de 8 segundos da Alexa.
    """
    message = build_command(action, config.HMAC_SECRET, params)
    client = _client("alexawol-lambda")
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        client.loop_start()
        info = client.publish(config.MQTT_CMD_TOPIC, message, qos=1)
        info.wait_for_publish(timeout=5)
        log.info("publicado: %s %s", action, params or {})
    finally:
        client.loop_stop()
        client.disconnect()


def read_state(timeout: float | None = None) -> dict | None:
    """Lê a mensagem retida de estado. Devolve None se não houver nenhuma.

    Sem retained significa que o agente nunca conectou — para nós, PC desligado.
    """
    timeout = config.STATE_READ_TIMEOUT if timeout is None else timeout
    received: dict = {}
    arrived = threading.Event()

    def on_connect(client, userdata, flags, reason_code, properties=None):
        client.subscribe(config.MQTT_STATE_TOPIC, qos=1)

    def on_message(client, userdata, message):
        try:
            received.update(json.loads(message.payload))
        except ValueError:
            log.warning("estado retido não é JSON válido")
        arrived.set()

    client = _client("alexawol-lambda-state")
    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(config.MQTT_HOST, config.MQTT_PORT, keepalive=30)
        client.loop_start()
        if not arrived.wait(timeout):
            log.info("nenhum estado retido em %.1fs; assumindo PC desligado", timeout)
            return None
        return received
    finally:
        client.loop_stop()
        client.disconnect()
