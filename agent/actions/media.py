"""Controle de mídia: abrir uma mídia e comandar a reprodução.

Duas camadas, nesta ordem de preferência:

**SMTC** (`GlobalSystemMediaTransportControlsSessionManager`) é a API de sessão de mídia do
Windows — a mesma que alimenta o overlay que aparece ao apertar as teclas de volume. Ela tem
`Play` e `Pause` explícitos, informa se está tocando e dá a posição da faixa. Não é específica
de player nenhum: qualquer aplicativo que se integre ao SMTC aparece ali, incluindo navegadores
tocando YouTube.

**Teclas de mídia** são o plano B, para o caso raro de um player que registra o atalho global
sem se integrar ao SMTC. São um canal cego: não dá para saber se algo respondeu, e play/pause é
uma tecla só que alterna.

O alvo do `play()` vem do `config.toml`, nunca da rede — ver o comentário em
`shared/protocol.py`.
"""

from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import subprocess
import time

log = logging.getLogger("alexawol")

# Sem janela de console piscando ao cair no fallback.
_NO_WINDOW = 0x08000000

# Teclas de mídia do Windows.
_VK_MEDIA_NEXT = 0xB0
_VK_MEDIA_PREV = 0xB1
_KEYEVENTF_KEYUP = 0x0002

# Acima disto, um comando de "anterior" apenas rebobina a faixa em vez de trocar — regra do
# Spotify e da maioria dos players. Abaixo, ele já troca.
_REBOBINA_ATE_SEGUNDOS = 3.0

# Intervalo entre dois comandos de "anterior" seguidos. Curto demais e o player junta os dois.
_INTERVALO_DUPLO = 0.30


# ---------------------------------------------------------------- abrir mídia


def play_target(target: str) -> None:
    """Abre a mídia configurada no aplicativo padrão do Windows.

    `os.startfile` delega ao ShellExecute, que resolve tanto caminho de arquivo quanto
    protocolo registrado — por isso serve para Spotify, navegador ou arquivo local sem
    integrar com player nenhum.
    """
    if not target:
        raise ValueError(
            "nenhuma mídia configurada — preencha [media].target no config.toml"
        )
    try:
        os.startfile(target)
    except (FileNotFoundError, OSError):
        # Para alguns URIs de protocolo o os.startfile levanta em vez de delegar ao shell.
        # A string vazia depois do `start` é o argumento de título: sem ela o cmd interpreta
        # um alvo entre aspas como nome de janela e não abre nada.
        subprocess.run(
            ["cmd", "/c", "start", "", target], check=True, creationflags=_NO_WINDOW
        )


# ---------------------------------------------------------------- SMTC


def _executar_smtc(operacao) -> bool:
    """Roda `operacao(sessão)` na sessão de mídia ativa. False se não deu para usar o SMTC.

    `operacao` é uma corrotina que recebe a sessão. Qualquer falha — pacote ausente, nenhuma
    sessão ativa, erro do WinRT — devolve False para o chamador decidir o plano B.
    """
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
        )
    except ImportError:
        log.debug("winrt não instalado; usando teclas de mídia")
        return False

    async def executar():
        manager = await Manager.request_async()
        sessao = manager.get_current_session()
        if sessao is None:
            log.info("nenhuma sessão de mídia ativa no Windows")
            return False
        # As chamadas try_*_async devolvem um booleano. Ignorá-lo faria uma recusa do
        # player passar por sucesso — e o chamador nem tentaria o plano B.
        resultado = await operacao(sessao)
        if resultado is False:
            log.warning("o player recusou o comando de mídia")
            return False
        return True

    try:
        return asyncio.run(executar())
    except Exception:
        log.exception("SMTC falhou; caindo para as teclas de mídia")
        return False


def _posicao_segundos(sessao) -> float:
    """Posição atual da faixa, em segundos."""
    pos = sessao.get_timeline_properties().position
    if hasattr(pos, "total_seconds"):
        return pos.total_seconds()
    return pos / 10_000_000  # o WinRT devolve em unidades de 100 ns


def esta_tocando() -> bool | None:
    """True tocando, False pausado, None se não há sessão ou o SMTC não está disponível."""
    resultado: list[bool] = []

    async def ler(sessao):
        # PlaybackStatus: 4 = Playing
        resultado.append(int(sessao.get_playback_info().playback_status) == 4)

    if _executar_smtc(ler) and resultado:
        return resultado[0]
    return None


# ---------------------------------------------------------------- teclas


def _tap(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, _KEYEVENTF_KEYUP, 0)


# ---------------------------------------------------------------- comandos


def play() -> None:
    """Retoma a reprodução.

    Só via SMTC. Não há tecla de "tocar" no Windows — a tecla de mídia é uma alternância, e
    usá-la aqui pausaria a música quando ela já estivesse tocando, que é o oposto do pedido.
    """
    async def op(sessao):
        return await sessao.try_play_async()

    if not _executar_smtc(op):
        raise RuntimeError(
            "não há sessão de mídia ativa no Windows — abra o player e comece a tocar algo"
        )


def pause() -> None:
    """Pausa a reprodução. Só via SMTC, pelo mesmo motivo do `play`."""
    async def op(sessao):
        return await sessao.try_pause_async()

    if not _executar_smtc(op):
        raise RuntimeError("não há sessão de mídia ativa no Windows")


def next_track() -> None:
    async def op(sessao):
        return await sessao.try_skip_next_async()

    if not _executar_smtc(op):
        _tap(_VK_MEDIA_NEXT)


def restart_track() -> None:
    """Recomeça a faixa atual do início."""
    async def op(sessao):
        if sessao.get_playback_info().controls.is_playback_position_enabled:
            return await sessao.try_change_playback_position_async(0)
        else:
            # Sem busca disponível: um "anterior" rebobina, desde que já tenha passado do
            # limiar. Antes disso a faixa já está no começo de qualquer forma.
            return await sessao.try_skip_previous_async()

    if not _executar_smtc(op):
        _tap(_VK_MEDIA_PREV)


def previous_track() -> None:
    """Vai para a faixa anterior de verdade.

    Com o SMTC dá para ler a posição e acertar sempre: passado o limiar, o primeiro comando só
    rebobina e é preciso um segundo; antes dele, um comando já troca de faixa. Sem o SMTC
    sobra o toque duplo às cegas, que retrocede duas faixas se a atual acabou de começar.
    """
    async def op(sessao):
        rebobina = _posicao_segundos(sessao) > _REBOBINA_ATE_SEGUNDOS
        ok = await sessao.try_skip_previous_async()
        if ok and rebobina:
            await asyncio.sleep(_INTERVALO_DUPLO)
            ok = await sessao.try_skip_previous_async()
        return ok

    if not _executar_smtc(op):
        _tap(_VK_MEDIA_PREV)
        time.sleep(_INTERVALO_DUPLO)
        _tap(_VK_MEDIA_PREV)
