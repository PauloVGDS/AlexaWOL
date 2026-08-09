"""Métricas do PC expostas no app da Alexa.

CPU, memória, disco e tempo ligado saem do `psutil` e custam microssegundos, então entram no
estado a cada publicação.

**GPU é diferente.** O uso vem do contador de desempenho do Windows, que serve para qualquer
fabricante — não depende de nvidia-smi nem do driver AMD. Mas ler custa ~2,5 s, tempo demais
para o caminho dos comandos. Por isso o valor é atualizado só pela thread periódica de estado,
por `atualizar_gpu()`, e `metricas()` apenas lê o cache sem nunca bloquear.

**Temperatura** exige o LibreHardwareMonitor rodando em segundo plano, que publica um namespace
WMI próprio. O `MSAcpi_ThermalZoneTemperature` responde "operação não suportada" na maioria dos
desktops, e placas AMD não têm equivalente ao nvidia-smi. Sem o LibreHardwareMonitor os campos
de temperatura simplesmente não aparecem.
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

# Depois disto o valor de GPU é considerado velho e deixa de ser publicado — melhor omitir do
# que mostrar um número parado no app.
_GPU_VALIDADE_S = 120

_gpu: dict = {"pct": None, "ts": 0.0}

# psutil.cpu_percent() sem intervalo compara com a chamada anterior. A primeira devolve 0,0,
# então "esquentamos" a medição no import para o primeiro estado publicado já valer.
psutil.cpu_percent(interval=None)


# ---------------------------------------------------------------- baratas


def uptime_minutos() -> int:
    return int((time.time() - psutil.boot_time()) // 60)


def cpu_percentual() -> int:
    return round(psutil.cpu_percent(interval=None))


def memoria_percentual() -> int:
    return round(psutil.virtual_memory().percent)


def disco_livre_percentual() -> int:
    """Percentual LIVRE no disco do sistema — o número que interessa num alerta."""
    raiz = os.environ.get("SystemDrive", "C:") + os.sep
    return round(100 - psutil.disk_usage(raiz).percent)


# ---------------------------------------------------------------- GPU


def atualizar_gpu() -> None:
    """Lê o uso da GPU e guarda no cache. Custa ~2,5 s — só chame de thread de fundo."""
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


# ---------------------------------------------------------------- temperaturas


def _temperaturas_lhm() -> dict:
    """Temperaturas do LibreHardwareMonitor, se ele estiver rodando."""
    try:
        import wmi  # type: ignore
    except ImportError:
        return {}

    for namespace in (r"root\LibreHardwareMonitor", r"root\OpenHardwareMonitor"):
        try:
            sensores = wmi.WMI(namespace=namespace).Sensor()
        except Exception:
            continue

        leituras: dict[str, list[float]] = {"cpu_temp": [], "gpu_temp": []}
        for s in sensores:
            if s.SensorType != "Temperature":
                continue
            nome = (s.Name or "").upper()
            if "GPU" in nome:
                leituras["gpu_temp"].append(s.Value)
            elif "CPU" in nome:
                leituras["cpu_temp"].append(s.Value)
        # O pico é o número que importa num painel de temperatura.
        return {k: round(max(v), 1) for k, v in leituras.items() if v}

    return {}


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
        ("ram_pct", memoria_percentual),
        ("disco_livre_pct", disco_livre_percentual),
        ("gpu_pct", gpu_percentual),
    ):
        try:
            valor = funcao()
        except Exception:
            log.exception("falha ao ler a métrica %s", nome)
            continue
        if valor is not None:
            resultado[nome] = valor

    try:
        resultado.update(_temperaturas_lhm())
    except Exception:
        log.exception("falha ao ler temperaturas")

    return resultado
