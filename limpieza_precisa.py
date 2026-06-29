# -*- coding: utf-8 -*-
"""Limpia comentarios por IDs especificos, conservando solo el ultimo PASS valido."""

import base64
import json
import os
import requests

with open("config.json", "r", encoding="utf-8-sig") as f:
    CONFIG = json.load(f)

ORG = CONFIG["organization"]
PROJ = CONFIG["project"]
BASE = f"https://dev.azure.com/{ORG}"
PAT = os.environ.get("AZURE_DEVOPS_PAT")


def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


def eliminar_comentario(tc_id, cid):
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments/{cid}?api-version=7.1-preview.4"
    r = requests.delete(url, headers=h_json(), timeout=15)
    return r.status_code in (200, 204)


# Plan de borrado: TC_ID -> [lista de comment_ids a borrar]
PLAN = {
    1177770: [
        22503303,  # andres tabares restrepo
        22503296,  # andres tabares
        22503278,  # Hamilton Tabares Villada
        22503263,  # Hamilton tabares
        22503251,  # Hamilton Tabares (FAIL)
        22503238,  # Hamilton Tabares (FAIL)
        22502315,  # Hamilton Tabares Villada
        22502314,  # Test de permisos
        # CONSERVAR: 22503312 (andres contreras PASS - el ultimo)
    ],
    1177771: [
        22503304,  # andres tabares restrepo FAIL
        22503297,  # andres tabares FAIL
        22503279,  # Hamilton Tabares Villada
        22503264,  # Hamilton tabares
        22503245,  # Hamilton Tabares FAIL
        22502318,  # Hamilton Tabares Villada
        # CONSERVAR: 22503313 (andres contreras PASS)
    ],
    1177772: [
        22503305,  # andres tabares restrepo
        22503298,  # andres tabares
        22503280,  # Hamilton Tabares Villada
        22503265,  # Hamilton tabares
        22503249,  # Hamilton Tabares FAIL
        22502319,  # Hamilton Tabares Villada
        # CONSERVAR: 22503314 (andres contreras PASS)
    ],
}

print()
print("=" * 70)
print("LIMPIEZA PRECISA DE COMENTARIOS")
print("=" * 70)
print()
print("Plan:")
total = sum(len(v) for v in PLAN.values())
for tc, ids in PLAN.items():
    print(f"  TC #{tc}: borrar {len(ids)} comentarios, conservar el ultimo PASS")
print(f"  Total a borrar: {total}")
print()

confirmar = input("Continuar? (s/n): ").strip().lower()
if confirmar != "s":
    print("[CANCELADO]")
    raise SystemExit(0)

print()
exitos = 0
fallos = 0
for tc_id, comment_ids in PLAN.items():
    print(f"\n[TC #{tc_id}]")
    for cid in comment_ids:
        ok = eliminar_comentario(tc_id, cid)
        if ok:
            print(f"  [OK] Borrado comment_id={cid}")
            exitos += 1
        else:
            print(f"  [FAIL] No se pudo borrar comment_id={cid}")
            fallos += 1

print()
print("=" * 70)
print(f"RESUMEN: {exitos} borrados | {fallos} fallidos")
print("=" * 70)
print()
print("Validando estado final de los TCs...")

import re
for tc_id in PLAN.keys():
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments?api-version=7.1-preview.4"
    r = requests.get(url, headers=h_json(), timeout=15)
    if r.status_code == 200:
        coms = r.json().get("comments", [])
        print(f"  TC #{tc_id}: {len(coms)} comentario(s) restante(s)")
        for c in coms:
            texto = re.sub(r"<[^>]+>", " ", c.get("text", ""))
            texto = re.sub(r"\s+", " ", texto)[:70]
            print(f"    - ID {c.get('id')}: {texto}")