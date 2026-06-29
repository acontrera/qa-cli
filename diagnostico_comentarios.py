# -*- coding: utf-8 -*-
import base64, json, os, requests

with open("config.json", "r", encoding="utf-8-sig") as f:
    CONFIG = json.load(f)

ORG = CONFIG["organization"]
PROJ = CONFIG["project"]
BASE = f"https://dev.azure.com/{ORG}"
PAT = os.environ.get("AZURE_DEVOPS_PAT")

def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}

for tc_id in [1177770, 1177771, 1177772]:
    print(f"\n{'='*60}")
    print(f"TC #{tc_id}")
    print('='*60)
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments?api-version=7.1-preview.4"
    r = requests.get(url, headers=h_json(), timeout=15)
    if r.status_code != 200:
        print(f"  [ERROR] {r.status_code}")
        continue
    comentarios = r.json().get("comments", [])
    print(f"  Total: {len(comentarios)} comentarios")
    for c in comentarios:
        cid = c.get("id")
        fecha = c.get("createdDate", "")[:19]
        texto = c.get("text", "")
        # Buscar pistas del comentario
        es_karate = "Karate" in texto or "qa-cli" in texto or "Exit code" in texto
        es_fail = "FAIL" in texto
        es_pass = "PASS" in texto
        flag = ""
        if es_karate and es_fail:
            flag = " <-- KARATE FAIL (basura)"
        elif es_karate and es_pass:
            flag = " <-- KARATE PASS (basura)"
        elif es_karate:
            flag = " <-- KARATE (revisar)"
        # Primeros 80 chars de texto plano
        import re
        texto_plano = re.sub(r"<[^>]+>", " ", texto)
        texto_plano = re.sub(r"\s+", " ", texto_plano)[:80]
        print(f"  - ID {cid} | {fecha} | {texto_plano}{flag}")