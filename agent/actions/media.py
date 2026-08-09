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

# Sem janela de console piscando ao cair no fallback.
_NO_WINDOW = 0x08000000

# Teclas de mídia do Windows. Funcionam com Spotify, YouTube, VLC e qualquer player que
# registre o atalho global — por isso não precisamos integrar com nenhum deles.
_VK_MEDIA_NEXT = 0xB0
_VK_MEDIA_PREV = 0xB1
_KEYEVENTF_KEYUP = 0x0002


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


def previous_track() -> None:
    _tap(_VK_MEDIA_PREV)


# Nota sobre play/pause: o Windows tem UMA tecla (VK_MEDIA_PLAY_PAUSE, 0xB3) que alterna,
# sem "tocar" e "pausar" separados. Expor as duas operações para a Alexa mapeando ambas no
# toggle produziria o comportamento errado — "pausar" com a música já pausada faria ela
# voltar a tocar. Fazer isso direito exige o SMTC do Windows
# (GlobalSystemMediaTransportControlsSessionManager), que tem Play e Pause explícitos e
# informa o estado atual, ao custo de uma dependência WinRT.
