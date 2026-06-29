# -*- coding: utf-8 -*-
"""Limpia comentarios Karate basura de TCs de pruebas."""

import argparse
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
if not PAT:
    from getpass import getpass
    PAT = getpass("PAT: ").strip()


def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}


def listar_comentarios(tc_id):
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments?api-version=7.1-preview.4"
    r = requests.get(url, headers=h_json(), timeout=15)
    return r.json().get("comments", []) if r.status_code == 200 else []


def eliminar_comentario(tc_id, cid):
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments/{cid}?api-version=7.1-preview.4"
    r = requests.delete(url, headers=h_json(), timeout=15)
    return r.status_code in (200, 204)


def cambiar_estado(tc_id, estado):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{"op": "add", "path": "/fields/System.State", "value": estado}]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tc_ids", nargs="+", type=int)
    ap.add_argument("--estado", default="Cerrado")
    args = ap.parse_args()

    print()
    print("=" * 60)
    print("LIMPIEZA DE COMENTARIOS KARATE BASURA")
    print("=" * 60)

    for tc_id in args.tc_ids:
        print(f"\n[TC #{tc_id}]")
        comentarios = listar_comentarios(tc_id)

        # Comentarios Karate basura
        a_borrar = [c for c in comentarios
                    if "Karate" in c.get("text", "") and "qa-cli" in c.get("text", "")
                    and ("FAIL" in c.get("text", "") or "Exit code" in c.get("text", ""))]

        print(f"  Comentarios Karate basura: {len(a_borrar)}")

        for c in a_borrar:
            ok = eliminar_comentario(tc_id, c["id"])
            print(f"    {'[OK]' if ok else '[FAIL]'} comment_id={c['id']}")

        if cambiar_estado(tc_id, args.estado):
            print(f"  [OK] Estado -> {args.estado}")

    print()
    print("=" * 60)
    print("LIMPIEZA TERMINADA")
    print("=" * 60)


if __name__ == "__main__":
    main()