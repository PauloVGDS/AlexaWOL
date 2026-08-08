"""Abre a mídia pré-configurada no aplicativo padrão do Windows.

O alvo vem do `config.toml`, nunca da rede — ver o comentário em `shared/protocol.py`. O
comando MQTT só diz "toque"; o que tocar é decisão local.

Serve para Spotify (`spotify:playlist:...`), navegador (`https://...`) ou arquivo local, sem
integrar com player nenhum: quem resolve é o shell do Windows.
"""

from __future__ import annotations

import os
import subprocess

# Sem janela de console piscando ao cair no fallback.
_NO_WINDOW = 0x08000000


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
