"""Volume e mudo do Windows via Core Audio (pycaw).

O endpoint é buscado a cada chamada de propósito: o dispositivo padrão muda quando você
conecta um fone Bluetooth ou troca a saída para HDMI, e queremos sempre agir sobre o que
está tocando agora.
"""

from __future__ import annotations

import comtypes
from pycaw.pycaw import AudioUtilities


def com_init() -> None:
    """Inicializa COM na thread atual.

    O paho entrega mensagens numa thread própria e o COM exige inicialização por thread,
    então o agente chama isto uma vez em cada thread que toca o áudio.
    """
    comtypes.CoInitialize()


def _endpoint():
    """IAudioEndpointVolume do dispositivo de saída padrão."""
    return AudioUtilities.GetSpeakers().EndpointVolume


def device_name() -> str:
    return AudioUtilities.GetSpeakers().FriendlyName


def get_volume() -> int:
    """Volume atual em 0-100."""
    return round(_endpoint().GetMasterVolumeLevelScalar() * 100)


def set_volume(percent: int) -> int:
    """Define o volume absoluto. Devolve o valor efetivamente aplicado."""
    percent = max(0, min(100, int(percent)))
    _endpoint().SetMasterVolumeLevelScalar(percent / 100.0, None)
    return percent


def adjust_volume(delta: int) -> int:
    """Soma `delta` ao volume atual, com saturação em 0 e 100."""
    endpoint = _endpoint()
    current = round(endpoint.GetMasterVolumeLevelScalar() * 100)
    target = max(0, min(100, current + int(delta)))
    endpoint.SetMasterVolumeLevelScalar(target / 100.0, None)
    return target


def get_mute() -> bool:
    return bool(_endpoint().GetMute())


def set_mute(muted: bool) -> bool:
    _endpoint().SetMute(1 if muted else 0, None)
    return bool(muted)
