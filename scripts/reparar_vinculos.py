"""
Script para mover TCs entre padres.
Uso: py reparar_vinculos.py <ID_PADRE_VIEJO> <ID_PADRE_NUEVO> <IDs_TC>
Ejemplo: py reparar_vinculos.py 1129661 1129575 1160584,1160885,1160886,1160887
"""

import requests, base64, os, sys
from getpass import getpass

ORG = "SuraColombia"
PROJ = "Gerencia_Tecnologia"
BASE = f"https://dev.azure.com/{ORG}"

PAT = os.environ.get("AZURE_DEVOPS_PAT") or getpass("PAT: ")


def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}


def obtener_wi(wid):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{wid}?$expand=relations&api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
    return r.json() if r.status_code == 200 else None


def reparar(padre_viejo, padre_nuevo, tc_id):
    wi = obtener_wi(tc_id)
    if not wi:
        return f"[ERROR] No se pudo obtener TC #{tc_id}"

    relaciones = wi.get("relations", [])
    indice_parent = None
    for i, rel in enumerate(relaciones):
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            id_padre = int(rel.get("url", "").split("/")[-1])
            if id_padre == padre_viejo:
                indice_parent = i
                break

    if indice_parent is None:
        return f"[WARN] TC #{tc_id} no tiene parent #{padre_viejo}"

    operaciones = [
        {"op": "remove", "path": f"/relations/{indice_parent}"},
        {"op": "add", "path": "/relations/-", "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"{BASE}/{PROJ}/_apis/wit/workItems/{padre_nuevo}"
        }}
    ]

    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    r = requests.patch(url, headers=h_patch(), json=operaciones, timeout=15)

    if r.status_code in (200, 201):
        return f"[OK] TC #{tc_id}: movido de #{padre_viejo} a #{padre_nuevo}"
    return f"[ERROR] TC #{tc_id}: {r.status_code} - {r.text[:150]}"


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: py reparar_vinculos.py <PADRE_VIEJO> <PADRE_NUEVO> <IDs separados por coma>")
        print("Ejemplo: py reparar_vinculos.py 1129661 1129575 1160584,1160885,1160886,1160887")
        sys.exit(1)

    padre_v = int(sys.argv[1])
    padre_n = int(sys.argv[2])
    tcs = [int(x.strip()) for x in sys.argv[3].split(",")]

    print(f"\n[INFO] Moviendo {len(tcs)} TCs de #{padre_v} a #{padre_n}")
    print("=" * 70)
    for tc in tcs:
        print(reparar(padre_v, padre_n, tc))
    print("=" * 70)
