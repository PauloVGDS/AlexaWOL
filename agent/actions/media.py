"""Abre a mídia pré-configurada no aplicativo padrão do Windows.

O alvo vem do `config.toml`, nunca da rede — ver o comentário em `shared/protocol.py`. O
comando MQTT só diz "toque"; o que tocar é decisão local.

Serve para Spotify (`spotify:playlist:...`), navegador (`https://...`) ou arquivo local, sem
integrar com player nenhum: quem resolve é o shell do Windows.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import time

# Sem janela de console piscando ao cair no fallback.
_NO_WINDOW = 0x08000000

# Teclas de mídia do Windows. Funcionam com Spotify, YouTube, VLC e qualquer player que
# registre o atalho global — por isso não precisamos integrar com nenhum deles.
_VK_MEDIA_NEXT = 0xB0
_VK_MEDIA_PREV = 0xB1
_KEYEVENTF_KEYUP = 0x0002

# Intervalo entre os dois toques de "anterior". Curto demais e o player junta os dois num só;
# longo demais e a experiência fica arrastada. 300 ms funciona no Spotify.
_PREV_DOUBLE_TAP_DELAY = 0.30


def play(target: str) -> None:
    if not target:
        raise ValueError(
            "nenhuma mídia configurada — preencha [media].target no config.toml"
        )

    try:
        os.startfile(target)
    except (FileNotFoundError, OSError):
        # `os.startfile` resolve caminhos de arquivo bem, mas para alguns URIs de protocolo
        # ele levanta em vez de delegar ao shell. O `start` do cmd sempre delega.
        # A string vazia é o argumento de título: sem ela o cmd interpreta um alvo entre
        # aspas como nome da janela e não abre nada.
        subprocess.run(
            ["cmd", "/c", "start", "", target], check=True, creationflags=_NO_WINDOW
        )


def _tap(vk: int) -> None:
    """Simula um toque na tecla de mídia — pressiona e solta."""
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


def next_track() -> None:
    _tap(_VK_MEDIA_NEXT)


def restart_track() -> None:
    """Recomeça a faixa atual do início.

    Um toque em "anterior" — que é o que a maioria dos players faz quando já se passaram
    alguns segundos da faixa.
    """
    _tap(_VK_MEDIA_PREV)


def previous_track() -> None:
    """Vai para a faixa anterior de verdade.

    Um toque só normalmente rebobina a faixa atual em vez de trocar, comportamento padrão do
    Spotify e da maioria dos players. O segundo toque, já com a posição no início, é o que
    efetivamente volta.

    Ressalva: se a faixa estiver tocando há poucos segundos, o primeiro toque já troca de
    faixa e o segundo volta mais uma — retrocedendo duas em vez de uma. Resolver isso exigiria
    ler a posição de reprodução, o que só o SMTC do Windows oferece (ver a nota no fim deste
    arquivo).
    """
    _tap(_VK_MEDIA_PREV)
    time.sleep(_PREV_DOUBLE_TAP_DELAY)
    _tap(_VK_MEDIA_PREV)


# Duas limitações têm a mesma origem: teclas de mídia são um canal cego, sem leitura de
# estado. O SMTC do Windows (GlobalSystemMediaTransportControlsSessionManager) resolveria as
# duas, ao custo de uma dependência WinRT e código assíncrono:
#
# 1. Play/pause. O Windows tem UMA tecla (VK_MEDIA_PLAY_PAUSE, 0xB3) que alterna, sem "tocar"
#    e "pausar" separados. Mapear as duas operações da Alexa nela faria "pausar" com a música
#    já pausada voltar a tocar. O SMTC tem TryPlayAsync e TryPauseAsync explícitos, e ainda
#    informa o estado — o que habilitaria o Alexa.PlaybackStateReporter.
#
# 2. O "voltar" por dois toques erra quando a faixa começou há poucos segundos, retrocedendo
#    duas em vez de uma. Com GetTimelineProperties().Position dava para decidir entre um e
#    dois toques conforme a posição de reprodução.
