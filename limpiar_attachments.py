# -*- coding: utf-8 -*-
"""Limpia attachments viejos, conserva solo el ultimo evidencia_v3.0."""

import base64
import json
import os
import re
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


def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}


def obtener_wi(tc_id):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?$expand=relations&api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
    return r.json() if r.status_code == 200 else None


def quitar_relacion(tc_id, indice_relacion):
    """Elimina una relacion (attachment) del work item por su indice."""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{"op": "remove", "path": f"/relations/{indice_relacion}"}]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)


# Por TC, definir cual GUID conservar (el legitimo del ultimo PASS)
A_CONSERVAR = {
    1177770: "86b6b27f-cab6-4d45-8cf8-690e14447bf6",  # evidencia_20260623_203735.json
    1177771: "0fa520c2-a3af-4a52-a18a-4cfa22b9a02d",  # evidencia_20260623_204241.json
    1177772: "192ea237-5bd8-44f9-a1ad-d6c6cfe2a180",  # evidencia_20260623_203846.json
}

print()
print("=" * 70)
print("LIMPIEZA DE ATTACHMENTS - CONSERVAR SOLO EL ULTIMO PASS")
print("=" * 70)

for tc_id, guid_conservar in A_CONSERVAR.items():
    print(f"\n[TC #{tc_id}]")
    print(f"  Conservar GUID: {guid_conservar}")

    wi = obtener_wi(tc_id)
    if not wi:
        print(f"  [ERROR] No se pudo leer el TC")
        continue

    relations = wi.get("relations", [])

    # Identificar indices de attachments a borrar (los que NO son el conservar)
    indices_a_borrar = []
    for i, rel in enumerate(relations):
        if rel.get("rel") == "AttachedFile":
            match = re.search(r"attachments/([^?]+)", rel.get("url", ""))
            guid = match.group(1) if match else ""
            if guid != guid_conservar:
                nombre = rel.get("attributes", {}).get("name", "?")
                indices_a_borrar.append((i, guid, nombre))

    print(f"  Attachments a borrar: {len(indices_a_borrar)}")

    if not indices_a_borrar:
        print(f"  [SKIP] Nada que limpiar")
        continue

    confirmar = input(f"  Borrar {len(indices_a_borrar)} attachments? (s/n): ").strip().lower()
    if confirmar != "s":
        print(f"  [SKIP] Cancelado")
        continue

    # IMPORTANTE: borrar en orden inverso (mayor a menor) porque los indices cambian
    indices_a_borrar.sort(key=lambda x: x[0], reverse=True)

    for i, guid, nombre in indices_a_borrar:
        ok = quitar_relacion(tc_id, i)
        estado = "[OK]" if ok else "[FAIL]"
        print(f"    {estado} idx={i} {nombre[:50]}")

    # Re-leer para verificar
    wi = obtener_wi(tc_id)
    attachments_restantes = [r for r in wi.get("relations", []) if r.get("rel") == "AttachedFile"]
    print(f"  Attachments restantes: {len(attachments_restantes)}")
    for r in attachments_restantes:
        print(f"    - {r.get('attributes', {}).get('name', '?')}")

print()
print("=" * 70)
print("LIMPIEZA TERMINADA")
print("=" * 70)