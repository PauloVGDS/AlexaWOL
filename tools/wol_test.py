#!/usr/bin/env python3
"""Envia um magic packet de Wake-on-LAN. Sem Alexa, sem nuvem, sem dependências.

Este é o primeiro teste do projeto e o mais importante: ele separa "o PC não acorda" de
"a skill não funciona". Rode a partir de OUTRA máquina da mesma rede — um notebook, ou o
próprio celular via Termux — com o PC alvo suspenso e depois desligado.

    python wol_test.py 00-11-22-33-44-55
    python wol_test.py 00-11-22-33-44-55 --broadcast 192.168.1.255

Se o PC acordar aqui, o hardware está certo e qualquer problema posterior é de software.
Se não acordar, nenhuma skill do mundo vai resolver — o caminho é o BIOS (procure por
"Power On by PCI-E", "Wake on LAN" ou "ErP" desabilitado).
"""

from __future__ import annotations

import argparse
import re
import socket


def magic_packet(mac: str) -> bytes:
    clean = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(clean) != 12:
        raise ValueError(f"MAC inválido: {mac!r} (esperados 12 dígitos hex)")
    return b"\xff" * 6 + bytes.fromhex(clean) * 16


def send(mac: str, broadcast: str, port: int) -> None:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Portas 9 e 7 são as convencionais; algumas placas só escutam uma delas, então
        # mandar nas duas custa nada e evita um falso negativo.
        for target_port in {port, 7, 9}:
            sock.sendto(packet, (broadcast, target_port))
            print(f"magic packet enviado para {mac} via {broadcast}:{target_port}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Envia um magic packet de Wake-on-LAN.")
    parser.add_argument("mac", help="MAC do alvo, ex.: 00-11-22-33-44-55")
    parser.add_argument(
        "--broadcast",
        default="255.255.255.255",
        help="endereço de broadcast (padrão: 255.255.255.255). Se não funcionar, use o "
        "broadcast da sua sub-rede, ex.: 192.168.1.255",
    )
    parser.add_argument("--port", type=int, default=9)
    args = parser.parse_args()
    send(args.mac, args.broadcast, args.port)


if __name__ == "__main__":
    main()
