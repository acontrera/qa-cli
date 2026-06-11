"""
Script para descubrir los nombres internos de los campos custom de Caso de Prueba.
Usa el TC ya creado #1160584 como referencia.
"""

import requests
import base64
import os
import json
import sys

ORGANIZATION = "SuraColombia"
PROJECT = "Gerencia_Tecnologia"
BASE_URL = f"https://dev.azure.com/{ORGANIZATION}"

PAT = os.environ.get("AZURE_DEVOPS_PAT")
if not PAT:
    from getpass import getpass
    PAT = getpass("PAT: ").strip()
if not PAT:
    sys.exit(1)


def headers():
    token = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


# Obtener el TC #1160584 con TODOS sus campos
print("[INFO] Consultando campos del TC #1160584...")
url = f"{BASE_URL}/{PROJECT}/_apis/wit/workitems/1160584?$expand=all&api-version=7.1"
r = requests.get(url, headers=headers(), timeout=15)

if r.status_code != 200:
    print(f"[ERROR] {r.status_code}: {r.text[:300]}")
    sys.exit(1)

data = r.json()
fields = data.get("fields", {})

# Buscar campos custom (los que NO empiezan con System. o Microsoft.)
custom_fields = {k: v for k, v in fields.items()
                 if not k.startswith("System.")
                 and not k.startswith("Microsoft.VSTS.")
                 and not k.startswith("WEF_")}

print("\n" + "=" * 70)
print("CAMPOS DEL TC #1160584")
print("=" * 70)

print("\n>>> CAMPOS ESTANDAR (importantes):")
for campo in ["System.Title", "System.State", "System.AreaPath",
              "System.IterationPath", "System.WorkItemType",
              "System.Description",
              "Microsoft.VSTS.Common.Priority"]:
    val = fields.get(campo, "N/A")
    if isinstance(val, str) and len(val) > 80:
        val = val[:80] + "..."
    print(f"  {campo:<50} = {val}")

print("\n>>> CAMPOS CUSTOM (nombres internos):")
if custom_fields:
    for nombre, valor in custom_fields.items():
        if isinstance(valor, str) and len(valor) > 60:
            valor = valor[:60] + "..."
        print(f"  {nombre:<50} = {valor}")
else:
    print("  (sin campos custom detectados)")

# Guardar todo en JSON para referencia
with open("campos_tc_referencia.json", "w", encoding="utf-8") as f:
    json.dump(fields, f, indent=2, ensure_ascii=False)

print("\n[OK] Detalle completo guardado en: campos_tc_referencia.json")
print("[INFO] Copia los nombres internos de los campos custom de arriba.")
