"""Métricas do PC expostas no app da Alexa.

CPU, memória, disco e tempo ligado saem do `psutil` e custam microssegundos, então entram no
estado a cada publicação.

**GPU é diferente.** O uso vem do contador de desempenho do Windows, que serve para qualquer
fabricante — não depende de nvidia-smi nem do driver AMD. Mas ler custa ~2,5 s, tempo demais
para o caminho dos comandos. Por isso o valor é atualizado só pela thread periódica de estado,
por `atualizar_gpu()`, e `metricas()` apenas lê o cache sem nunca bloquear.

Temperatura ficou de fora de propósito: o Windows não a expõe de forma confiável — o
`MSAcpi_ThermalZoneTemperature` responde "operação não suportada" na maioria dos desktops e
placas AMD não têm equivalente ao nvidia-smi. A única fonte seria o LibreHardwareMonitor
rodando em segundo plano, e exigir um app extra não compensa por um número.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time

import psutil

log = logging.getLogger("alexawol")

_SEM_JANELA = 0x08000000

# Soma a utilização de todos os "engines" da GPU (3D, cópia, decodificação, ...).
_PS_GPU = (
    "(Get-Counter '\\GPU Engine(*)\\Utilization Percentage')"
    ".CounterSamples | Measure-Object CookedValue -Sum | "
    "Select-Object -ExpandProperty Sum"
)

# Com que frequência a GPU é relida. Deliberadamente muito maior que o ciclo de estado: a
# leitura custa ~2,5 s de CPU e responde por quase todo o consumo do agente, enquanto o número
# em si é de painel — ninguém precisa dele fresco a cada 30 s. Medido: a 30 s o agente ocupava
# 4,8% de um núcleo; a 120 s cai para cerca de um quarto disso.
_GPU_INTERVALO_S = 120

# Depois disto o valor é considerado velho e deixa de ser publicado — melhor omitir do que
# mostrar um número parado no app. Precisa ser maior que o intervalo de releitura.
_GPU_VALIDADE_S = 300

_gpu: dict = {"pct": None, "ts": 0.0}

# psutil.cpu_percent() sem intervalo compara com a chamada anterior. A primeira devolve 0,0,
# então "esquentamos" a medição no import para o primeiro estado publicado já valer.
psutil.cpu_percent(interval=None)


# ---------------------------------------------------------------- baratas


def uptime_minutos() -> int:
    return int((time.time() - psutil.boot_time()) // 60)


def cpu_percentual() -> int:
    return round(psutil.cpu_percent(interval=None))


def _gb(bytes_: int) -> int:
    """Bytes para gigabytes, como os fabricantes contam (1 GB = 10^9)."""
    return round(bytes_ / 1_000_000_000)


def memoria_usada_gb() -> int:
    return _gb(psutil.virtual_memory().used)


def memoria_total_gb() -> int:
    return _gb(psutil.virtual_memory().total)


def _disco():
    raiz = os.environ.get("SystemDrive", "C:") + os.sep
    return psutil.disk_usage(raiz)


def disco_usado_gb() -> int:
    return _gb(_disco().used)


def disco_total_gb() -> int:
    return _gb(_disco().total)


# ---------------------------------------------------------------- GPU


def atualizar_gpu(forcar: bool = False) -> None:
    """Relê o uso da GPU se já passou o intervalo. Custa ~2,5 s — só de thread de fundo.

    A limitação de frequência mora aqui, e não no chamador, para que o laço do agente
    continue simples e ninguém consiga tornar a leitura cara por engano.
    """
    if not forcar and time.time() - _gpu["ts"] < _GPU_INTERVALO_S:
        return
    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _PS_GPU],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=_SEM_JANELA,
        )
        # A saída sai com vírgula decimal em locale pt-BR.
        bruto = resultado.stdout.strip().replace(",", ".")
        _gpu["pct"] = round(min(100.0, max(0.0, float(bruto))))
        _gpu["ts"] = time.time()
    except Exception:
        log.exception("falha ao ler o uso da GPU")


def gpu_percentual() -> int | None:
    if _gpu["pct"] is None or time.time() - _gpu["ts"] > _GPU_VALIDADE_S:
        return None
    return _gpu["pct"]


# ---------------------------------------------------------------- agregado


def metricas() -> dict:
    """Todas as métricas disponíveis, prontas para o estado publicado.

    Campos que falham individualmente são omitidos em vez de derrubar o estado inteiro — um
    disco inacessível não pode impedir o relato do volume.
    """
    resultado: dict = {}
    for nome, funcao in (
        ("uptime_min", uptime_minutos),
        ("cpu_pct", cpu_percentual),
        ("gpu_pct", gpu_percentual),
        ("ram_usada_gb", memoria_usada_gb),
        ("ram_total_gb", memoria_total_gb),
        ("disco_usado_gb", disco_usado_gb),
        ("disco_total_gb", disco_total_gb),
    ):
        try:
            valor = funcao()
        except Exception:
            log.exception("falha ao ler a métrica %s", nome)
            continue
        if valor is not None:
            resultado[nome] = valor

    return resultado
