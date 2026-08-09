#!/usr/bin/env python3
"""Verifica que as listas que precisam andar juntas não saíram de sincronia.

O projeto tem várias definições que se espelham em arquivos diferentes — allowlist e
dispatch, métricas do Lambda e campos publicados pelo agente, dependências e verificador.
Nenhuma dessas divergências quebra a importação nem aparece em teste funcional: elas se
manifestam como comando recusado, mostrador vazio ou agente que não sobe.

Foi assim que o `scene.py` quase suspendeu o PC ao pedir música — uma lista e um mapa
saíram de sincronia e tudo continuou passando.

    python tests/test_consistencia.py
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "lambda"))

os.environ.setdefault("PC_MAC", "00-11-22-33-44-55")
for chave in ("LWA_CLIENT_ID", "LWA_CLIENT_SECRET", "MQTT_HOST",
              "MQTT_USERNAME", "MQTT_PASSWORD", "HMAC_SECRET"):
    os.environ.setdefault(chave, "x")

from shared.protocol import ACTIONS  # noqa: E402
from alexa import metrics, scene  # noqa: E402

falhas = 0


def conferir(rotulo: str, faltando: set, mensagem: str) -> None:
    global falhas
    if not faltando:
        print(f"  OK       {rotulo}")
    else:
        falhas += 1
        print(f"  FALHOU   {rotulo}: {sorted(faltando)} — {mensagem}")


def ler(caminho: str) -> str:
    return (REPO / caminho).read_text(encoding="utf-8")


print("Allowlist e dispatch:")
dispatch = set(re.findall(r'action == "(\w+)"', ler("agent/alexawol_agent.py")))
conferir("toda ação da allowlist é tratada", ACTIONS - dispatch,
         "o agente recusaria o comando com 'ação não tratada'")
conferir("todo ramo do dispatch está na allowlist", dispatch - ACTIONS,
         "o comando seria recusado antes de chegar no dispatch")

print("Ferramenta de teste manual:")
bloco = ler("tools/send_cmd.py")
bloco = bloco[bloco.find("choices=["):]
bloco = bloco[:bloco.find("]")]
escolhas = set(re.findall(r'"(\w+)"', bloco))
conferir("toda ação pode ser testada pelo send_cmd", ACTIONS - escolhas,
         "não haveria como exercitar a ação sem a Alexa")
conferir("send_cmd não oferece ação inexistente", escolhas - ACTIONS,
         "publicaria um comando que o agente recusa")

print("Métricas do Lambda e do agente:")
publicados = set(re.findall(r'\("(\w+)", \w+\)', ler("agent/actions/system.py")))
esperados = {m["campo"] for m in metrics.METRICAS}
conferir("todo campo esperado é publicado", esperados - publicados,
         "o mostrador ficaria sempre vazio no app")
conferir("todo campo publicado é usado", publicados - esperados,
         "o agente gastaria tempo medindo algo que ninguém lê")

print("Cenas:")
endpoints_cena = set(scene._ACTION_BY_ENDPOINT.values())
conferir("toda ação de cena está na allowlist", endpoints_cena - ACTIONS,
         "a cena publicaria um comando que o agente recusa")

print("Dependências e verificador:")
pacotes = {
    linha.split(">=")[0].split("==")[0].strip().lower()
    for linha in ler("agent/requirements.txt").splitlines()
    if linha.strip() and not linha.startswith("#")
}
verificador = ler("tools/check_requisitos.ps1")
# winrt é opcional: sem ele o agente sobe e perde só o play/pause.
obrigatorios = {p for p in pacotes if not p.startswith("winrt")}
nao_verificados = {p for p in obrigatorios if p not in verificador}
conferir("todo pacote obrigatório é verificado", nao_verificados,
         "faltando, o agente morre em silêncio — roda por pythonw, sem console")

print()
if falhas:
    print(f"{falhas} inconsistência(s).")
    sys.exit(1)
print("Tudo em sincronia.")
