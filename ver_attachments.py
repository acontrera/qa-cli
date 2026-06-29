# -*- coding: utf-8 -*-
import base64, json, os, requests, re

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

    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?$expand=relations&api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
    if r.status_code != 200:
        print(f"  [ERROR] {r.status_code}")
        continue

    relations = r.json().get("relations", [])
    attachments = [rel for rel in relations if rel.get("rel") == "AttachedFile"]

    print(f"  Total attachments: {len(attachments)}")
    for i, att in enumerate(attachments, 1):
        nombre = att.get("attributes", {}).get("name", "?")
        comment = att.get("attributes", {}).get("comment", "")
        att_id = att.get("attributes", {}).get("id", "?")
        # Extraer GUID del URL para borrar luego
        match = re.search(r"attachments/([^?]+)", att.get("url", ""))
        guid = match.group(1) if match else "?"
        print(f"  {i}. {nombre}")
        print(f"     Comment: {comment[:60]}")
        print(f"     GUID: {guid}")