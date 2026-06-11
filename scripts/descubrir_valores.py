"""Descubre los valores permitidos de los campos custom de Caso de prueba."""
import requests, base64, os, sys
from getpass import getpass

PAT = os.environ.get("AZURE_DEVOPS_PAT") or getpass("PAT: ")
token = base64.b64encode(f":{PAT}".encode()).decode()
h = {"Authorization": f"Basic {token}"}

ORG = "SuraColombia"
PROJ = "Gerencia_Tecnologia"
BASE = f"https://dev.azure.com/{ORG}"

# Obtener el work item type "Caso de prueba" con sus campos
url = f"{BASE}/{PROJ}/_apis/wit/workitemtypes/Caso%20de%20prueba/fields?$expand=allowedValues&api-version=7.1"
r = requests.get(url, headers=h, timeout=15)

if r.status_code != 200:
    print(f"[ERROR] {r.status_code}: {r.text[:200]}")
    sys.exit(1)

campos = r.json().get("value", [])

# Buscar los campos custom
buscar = {
    "Custom.Fase": "Fase",
    "Custom.Niveldeprueba": "Nivel de prueba",
    "Custom.Prioridaddecaso": "Prioridad de caso",
    "Custom.886da9bd-0220-4a21-b0c7-1d93ecdf4390": "Tipo de ejecucion",
}

print("\n" + "=" * 70)
print("VALORES PERMITIDOS POR CAMPO")
print("=" * 70)

for campo in campos:
    ref = campo.get("referenceName", "")
    if ref in buscar:
        nombre = buscar[ref]
        valores = campo.get("allowedValues", [])
        print(f"\n>>> {nombre} ({ref}):")
        if valores:
            for v in valores:
                print(f"    - {repr(v)}")
        else:
            print("    (campo de texto libre o sin restriccion)")
