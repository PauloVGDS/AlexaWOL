"""Métricas do PC exibidas no app da Alexa.

**Fonte única de verdade.** O `discovery.py` monta as capabilities a partir daqui e o
`state.py` monta as propriedades a partir daqui. Definir nos dois lugares seria repetir o erro
que o `scene.py` já cometeu, em que uma lista e um mapa saíram de sincronia.

Cada métrica vira uma instância de `Alexa.RangeController` com `nonControllable: true` — ou
seja, o app mostra o valor mas não deixa alterar, que é o que queremos. Como efeito colateral
útil, dá para perguntar por voz: "Alexa, qual é o tempo ligado do computador?"
"""

from __future__ import annotations

# A ORDEM AQUI É A ORDEM NO APP: o card renderiza os controles na sequência em que eles
# aparecem no Discovery. Não existe cabeçalho de seção no Smart Home API, então o agrupamento
# é feito por vizinhança e por prefixo no nome — "Uso atual do..." mantém processador e placa
# de vídeo lendo como um bloco só.
#
# `campo` é a chave publicada pelo agente na mensagem retida de estado.
METRICAS = (
    # -- desempenho
    {
        "instance": "PC.CPU",
        "campo": "cpu_pct",
        "nomes": {"pt-BR": "Uso atual do processador", "en-US": "Current CPU usage"},
        "minimo": 0,
        "maximo": 100,
    },
    {
        "instance": "PC.GPU",
        "campo": "gpu_pct",
        "nomes": {"pt-BR": "Uso atual da placa de vídeo", "en-US": "Current GPU usage"},
        "minimo": 0,
        "maximo": 100,
    },
    # -- armazenamento
    {
        "instance": "PC.DiscoUsado",
        "campo": "disco_usado_gb",
        "nomes": {"pt-BR": "Disco usado em gigabytes", "en-US": "Disk used in gigabytes"},
        "minimo": 0,
        "maximo": 65536,
    },
    {
        "instance": "PC.DiscoTotal",
        "campo": "disco_total_gb",
        "nomes": {"pt-BR": "Disco total em gigabytes", "en-US": "Total disk in gigabytes"},
        "minimo": 0,
        "maximo": 65536,
    },
    {
        "instance": "PC.RAMUsada",
        "campo": "ram_usada_gb",
        "nomes": {"pt-BR": "Memória usada em gigabytes", "en-US": "Memory used in gigabytes"},
        "minimo": 0,
        "maximo": 1024,
    },
    {
        "instance": "PC.RAMTotal",
        "campo": "ram_total_gb",
        "nomes": {"pt-BR": "Memória total em gigabytes", "en-US": "Total memory in gigabytes"},
        "minimo": 0,
        "maximo": 1024,
    },
    # -- por último, o que muda devagar
    {
        "instance": "PC.Uptime",
        "campo": "uptime_min",
        "nomes": {"pt-BR": "Tempo ligado em minutos", "en-US": "Uptime in minutes"},
        "minimo": 0,
        "maximo": 43200,  # 30 dias
    },
)


def capability(metrica: dict) -> dict:
    """Capability de Discovery para uma métrica."""
    # Sem unitOfMeasure de propósito. O único asset aplicável seria Alexa.Unit.Percent, que
    # o app renderiza como a palavra "Por cento" — e não existe asset para gigabytes. A
    # unidade vai no próprio nome, onde ela é lida com naturalidade e também funciona por voz.
    configuracao: dict = {
        "supportedRange": {
            "minimumValue": metrica["minimo"],
            "maximumValue": metrica["maximo"],
            "precision": 1,
        }
    }

    return {
        "type": "AlexaInterface",
        "interface": "Alexa.RangeController",
        "instance": metrica["instance"],
        "version": "3",
        "properties": {
            "supported": [{"name": "rangeValue"}],
            "proactivelyReported": False,
            "retrievable": True,
            # É o que transforma o controle em mostrador: o app exibe, mas não deixa mexer.
            "nonControllable": True,
        },
        "capabilityResources": {
            "friendlyNames": [
                {"@type": "text", "value": {"text": texto, "locale": locale}}
                for locale, texto in metrica["nomes"].items()
            ]
        },
        "configuration": configuracao,
    }


def capabilities() -> list[dict]:
    return [capability(m) for m in METRICAS]
