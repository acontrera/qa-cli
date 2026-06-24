"""
Descubre los estados disponibles para Caso de Prueba en Sura ADO.
Necesario antes de programar cambio de estado de TCs.
"""
import requests, base64, os, sys, json
from getpass import getpass

# Cargar config
with open("config.json", "r", encoding="utf-8-sig") as f:
    cfg = json.load(f)

ORG = cfg["organization"]
PROJ = cfg["project"]
BASE = f"https://dev.azure.com/{ORG}"

PAT = os.environ.get("AZURE_DEVOPS_PAT") or getpass("PAT: ")
token = base64.b64encode(f":{PAT}".encode()).decode()
h = {"Authorization": f"Basic {token}"}

# Obtener estados del work item type "Caso de prueba"
url = f"{BASE}/{PROJ}/_apis/wit/workitemtypes/Caso%20de%20prueba/states?api-version=7.1"
r = requests.get(url, headers=h, timeout=15)

if r.status_code != 200:
    print(f"[ERROR] {r.status_code}: {r.text[:300]}")
    sys.exit(1)

estados = r.json().get("value", [])

print()
print("=" * 60)
print("ESTADOS DISPONIBLES PARA 'Caso de prueba'")
print("=" * 60)
print()
print(f"{'Nombre':<25} {'Categoria':<20} {'Color':<10}")
print("-" * 60)

for e in estados:
    nombre = e.get("name", "")
    categoria = e.get("category", "")
    color = e.get("color", "")
    print(f"{nombre:<25} {categoria:<20} #{color}")

print()
print("Mapeo a categorias estandar de ADO:")
print("  Proposed   = TCs nuevos/no asignados")
print("  InProgress = TCs en ejecucion/desarrollo")
print("  Resolved   = TCs ejecutados con bug pendiente")
print("  Completed  = TCs cerrados/finalizados")
print("  Removed    = TCs eliminados")
print()
print("Recomendacion:")
print("  - Para PASS: usar estado con categoria 'Completed' (ej: Cerrado)")
print("  - Para FAIL: usar estado con categoria 'Resolved' o similar")