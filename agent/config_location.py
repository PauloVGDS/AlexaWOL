"""Onde mora o `config.toml`, e por que não onde você esperaria.

O arquivo concentra as duas credenciais MQTT e o segredo HMAC. O `.gitignore` impede que ele
vá para o repositório, mas **não impede que ele saia da máquina**: se o projeto estiver dentro
de OneDrive, Dropbox ou Google Drive, o arquivo é sincronizado para a nuvem do serviço e para
todo dispositivo logado naquela conta. Isso é exatamente o que a separação de credenciais
existe para evitar.

Por isso o local padrão fica fora da árvore do projeto, em `%LOCALAPPDATA%`, que nenhum desses
serviços sincroniza.

Módulo do lado do PC apenas — o Lambda não usa nada daqui.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "ALEXAWOL_CONFIG"

# Marcadores de pasta sincronizada. Cobrem os serviços comuns no Windows; a checagem é por
# nome de diretório porque é o que funciona sem depender de API de cada serviço.
_SYNC_MARKERS = ("onedrive", "dropbox", "google drive", "googledrive", "iclouddrive")


def default_path() -> Path:
    """Local recomendado: fora de qualquer pasta sincronizada."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "AlexaWOL" / "config.toml"
    return legacy_path()


def legacy_path() -> Path:
    """Local antigo, dentro do projeto. Mantido para quem já tinha o arquivo ali."""
    return Path(__file__).resolve().parent / "config.toml"


def resolve(explicit: str | None = None) -> Path:
    """Descobre qual config usar, em ordem de precedência."""
    if explicit:
        return Path(explicit)
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env)
    preferred = default_path()
    if preferred.exists():
        return preferred
    return legacy_path()


def sync_service(path: Path) -> str | None:
    """Nome do serviço de sincronização que cobre `path`, ou None.

    Confere primeiro as variáveis que o próprio OneDrive publica, e depois cai numa
    heurística por nome de diretório para os demais serviços.
    """
    resolved = str(path.resolve()).lower()

    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        root = os.environ.get(var)
        if root and resolved.startswith(str(Path(root).resolve()).lower()):
            return "OneDrive"

    for part in path.resolve().parts:
        if part.lower() in _SYNC_MARKERS:
            return part

    return None


def warning_if_synced(path: Path) -> str | None:
    """Mensagem de alerta se o config estiver numa pasta sincronizada."""
    service = sync_service(path)
    if not service:
        return None
    return (
        f"ATENÇÃO: {path} está dentro de uma pasta do {service}.\n"
        f"         Esse arquivo guarda as duas credenciais MQTT e o segredo HMAC, e está\n"
        f"         sendo sincronizado para a nuvem e para os outros dispositivos da conta.\n"
        f"         Mova para: {default_path()}"
    )
