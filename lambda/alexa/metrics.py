"""Métricas do PC exibidas no app da Alexa.

**Fonte única de verdade.** O `discovery.py` monta as capabilities a partir daqui e o
`state.py` monta as propriedades a partir daqui. Definir nos dois lugares seria repetir o erro
que o `scene.py` já cometeu, em que uma lista e um mapa saíram de sincronia.

Cada métrica vira uma instância de `Alexa.RangeController` com `nonControllable: true` — ou
seja, o app mostra o valor mas não deixa alterar, que é o que queremos. Como efeito colateral
útil, dá para perguntar por voz: "Alexa, qual é o tempo ligado do computador?"
"""

from __future__ import annotations

# `campo` é a chave publicada pelo agente na mensagem retida de estado.
METRICAS = (
    {
        "instance": "PC.Uptime",
        "campo": "uptime_min",
        "nomes": {"pt-BR": "tempo ligado", "en-US": "uptime"},
        "minimo": 0,
        "maximo": 43200,  # 30 dias em minutos
        "unidade": None,
    },
    {
        "instance": "PC.CPU",
        "campo": "cpu_pct",
        "nomes": {"pt-BR": "uso do processador", "en-US": "CPU usage"},
        "minimo": 0,
        "maximo": 100,
        "unidade": "Alexa.Unit.Percent",
    },
    {
        "instance": "PC.RAM",
        "campo": "ram_pct",
        "nomes": {"pt-BR": "uso de memória", "en-US": "memory usage"},
        "minimo": 0,
        "maximo": 100,
        "unidade": "Alexa.Unit.Percent",
    },
    {
        "instance": "PC.Disk",
        "campo": "disco_livre_pct",
        "nomes": {"pt-BR": "espaço livre em disco", "en-US": "free disk space"},
        "minimo": 0,
        "maximo": 100,
        "unidade": "Alexa.Unit.Percent",
    },
    {
        "instance": "PC.GPU",
        "campo": "gpu_pct",
        "nomes": {"pt-BR": "uso da placa de vídeo", "en-US": "GPU usage"},
        "minimo": 0,
        "maximo": 100,
        "unidade": "Alexa.Unit.Percent",
    },
)


def capability(metrica: dict) -> dict:
    """Capability de Discovery para uma métrica."""
    configuracao: dict = {
        "supportedRange": {
            "minimumValue": metrica["minimo"],
            "maximumValue": metrica["maximo"],
            "precision": 1,
        }
    }
    if metrica["unidade"]:
        configuracao["unitOfMeasure"] = metrica["unidade"]

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
