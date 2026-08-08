"""Desligar, reiniciar e suspender o Windows.

O desligamento é sempre agendado com alguns segundos de folga e pode ser cancelado por
`abort`. Essa janela é o que impede um comando espúrio de derrubar a máquina sem recurso.
"""

from __future__ import annotations

import ctypes
import subprocess

# Sem janela de console ao chamar shutdown.exe a partir de um processo sem terminal.
_NO_WINDOW = 0x08000000


def _run(args: list[str]) -> None:
    subprocess.run(args, check=True, creationflags=_NO_WINDOW)


def shutdown(delay: int = 20, force: bool = False) -> None:
    args = ["shutdown", "/s", "/t", str(max(0, int(delay)))]
    if force:
        args.append("/f")
    _run(args)


def restart(delay: int = 20, force: bool = False) -> None:
    args = ["shutdown", "/r", "/t", str(max(0, int(delay)))]
    if force:
        args.append("/f")
    _run(args)


def abort() -> None:
    """Cancela um desligamento ou reinício agendado.

    Falha se não houver nada agendado, o que é esperado — o chamador ignora.
    """
    subprocess.run(["shutdown", "/a"], check=False, creationflags=_NO_WINDOW)


def suspend() -> None:
    """Suspende para a RAM (S3).

    SetSuspendState(bHibernate, bForce, bWakeupEventsDisabled). O terceiro parâmetro é o
    que importa aqui: precisa ser 0, senão o Windows desarma os eventos de wake e o
    Wake-on-LAN não traz a máquina de volta.

    Ressalva conhecida: com a hibernação habilitada, o Windows pode hibernar (S4) em vez de
    suspender. Na prática o WOL funciona igual nos dois estados, desde que a placa de rede
    esteja armada. Se você quiser garantir S3, rode `powercfg -h off`.
    """
    ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
