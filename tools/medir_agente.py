#!/usr/bin/env python3
"""Mede o custo real do agente: CPU, memória e o peso da leitura de GPU.

O agente passa quase todo o tempo bloqueado esperando rede, mas acorda a cada 30 s para
publicar estado — e nesse ciclo dispara um PowerShell para ler o uso da GPU. Este script
separa as duas coisas, porque o subprocesso não aparece na conta do processo principal.

    python tools\\medir_agente.py            # janela padrão de 70 s (2+ ciclos)
    python tools\\medir_agente.py --segundos 150
"""

from __future__ import annotations

import argparse
import time

import psutil


def achar_agente() -> psutil.Process | None:
    for p in psutil.process_iter(["name", "cmdline"]):
        if not (p.info["name"] or "").lower().startswith("python"):
            continue
        linha = " ".join(p.info["cmdline"] or [])
        if "alexawol_agent" in linha:
            return p
    # A tarefa agendada roda pythonw sem cmdline visível; cai no processo solto.
    candidatos = [
        p for p in psutil.process_iter(["name"])
        if (p.info["name"] or "").lower() == "pythonw.exe"
    ]
    return candidatos[0] if len(candidatos) == 1 else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Mede o custo do agente AlexaWOL.")
    parser.add_argument("--segundos", type=int, default=70)
    args = parser.parse_args()

    agente = achar_agente()
    if agente is None:
        raise SystemExit("agente não encontrado — ele está rodando?")

    nucleos = psutil.cpu_count()
    print(f"agente PID {agente.pid}   |   {nucleos} núcleos lógicos")
    print(f"medindo por {args.segundos}s...\n")

    inicio = agente.cpu_times()
    t0 = time.time()

    # Filhos (o PowerShell da GPU) nascem e morrem entre amostras, então acumulamos o tempo
    # de CPU de cada um enquanto ele existe.
    filhos_vistos: dict[int, float] = {}
    pico_rss = 0

    while time.time() - t0 < args.segundos:
        try:
            pico_rss = max(pico_rss, agente.memory_info().rss)
            for filho in agente.children(recursive=True):
                try:
                    tempos = filho.cpu_times()
                    filhos_vistos[filho.pid] = tempos.user + tempos.system
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except psutil.NoSuchProcess:
            raise SystemExit("o agente morreu durante a medição")
        time.sleep(0.2)

    fim = agente.cpu_times()
    decorrido = time.time() - t0

    cpu_proprio = (fim.user - inicio.user) + (fim.system - inicio.system)
    cpu_filhos = sum(filhos_vistos.values())
    total = cpu_proprio + cpu_filhos

    print(f"janela medida        : {decorrido:.0f}s")
    print(f"CPU do processo      : {cpu_proprio:.2f}s")
    print(f"CPU dos subprocessos : {cpu_filhos:.2f}s  ({len(filhos_vistos)} PowerShell da GPU)")
    print(f"CPU total            : {total:.2f}s")
    print()
    print(f"ocupação de 1 núcleo : {100 * total / decorrido:.2f}%")
    print(f"do processador todo  : {100 * total / (decorrido * nucleos):.3f}%")
    print(f"memória (pico RSS)   : {pico_rss / 1024 / 1024:.0f} MB")


if __name__ == "__main__":
    main()
