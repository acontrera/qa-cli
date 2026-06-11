"""
Script para asignar Work Items existentes a un usuario.
Uso:
    py asignar_tcs.py <IDs separados por coma>
    py asignar_tcs.py --hu <ID_HU>     (asigna TODOS los TC hijos del contenedor de esa HU)

Ejemplos:
    py asignar_tcs.py 1160899,1160900,1160901
    py asignar_tcs.py --hu 1129578     (asigna todos los TC hijos de Pruebas de calidad de la HU)
"""

import requests, base64, os, sys
from getpass import getpass

ORG = "SuraColombia"
PROJ = "Gerencia_Tecnologia"
BASE = f"https://dev.azure.com/{ORG}"

ASSIGNED_TO_EMAIL = "afcontreras@sura.com.co"

PAT = os.environ.get("AZURE_DEVOPS_PAT") or getpass("PAT: ")


def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}


def asignar_tc(tc_id):
    """Asigna un TC al usuario configurado."""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    operaciones = [
        {"op": "add", "path": "/fields/System.AssignedTo", "value": ASSIGNED_TO_EMAIL}
    ]
    r = requests.patch(url, headers=h_patch(), json=operaciones, timeout=15)

    if r.status_code in (200, 201):
        data = r.json()
        titulo = data.get("fields", {}).get("System.Title", "")[:60]
        return f"[OK] #{tc_id} asignado: {titulo}"
    else:
        return f"[ERROR] #{tc_id}: {r.status_code} - {r.text[:200]}"


def obtener_hijos_tcs(parent_id):
    """Obtiene IDs de los hijos tipo 'Caso de prueba' de un work item."""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{parent_id}?$expand=relations&api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
    if r.status_code != 200:
        return []

    data = r.json()
    relaciones = data.get("relations", [])
    hijos_ids = []
    for rel in relaciones:
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Forward":
            hijos_ids.append(int(rel["url"].split("/")[-1]))

    if not hijos_ids:
        return []

    # Obtener detalles para filtrar solo Casos de Prueba
    ids_str = ",".join(str(i) for i in hijos_ids)
    url2 = f"{BASE}/{PROJ}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.WorkItemType,System.Title&api-version=7.1"
    r2 = requests.get(url2, headers=h_json(), timeout=15)
    if r2.status_code != 200:
        return []

    items = r2.json().get("value", [])
    tcs = []
    for item in items:
        f = item.get("fields", {})
        if f.get("System.WorkItemType") == "Caso de prueba":
            tcs.append(item.get("id"))

    return tcs


def buscar_contenedor_pruebas_calidad(hu_id):
    """Busca el contenedor 'Pruebas de calidad' hijo de una HU."""
    tcs_hijos_hu = obtener_hijos_tcs(hu_id)
    if not tcs_hijos_hu:
        return None

    # Buscar el que se llame "Pruebas de calidad"
    ids_str = ",".join(str(i) for i in tcs_hijos_hu)
    url = f"{BASE}/{PROJ}/_apis/wit/workitems?ids={ids_str}&fields=System.Id,System.Title&api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
    if r.status_code != 200:
        return None

    items = r.json().get("value", [])
    for item in items:
        titulo = item.get("fields", {}).get("System.Title", "")
        if "pruebas de calidad" in titulo.lower():
            return item.get("id")
    return None


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("\nUso:")
        print("  py asignar_tcs.py <IDs separados por coma>")
        print("  py asignar_tcs.py --hu <ID_HU>")
        print("")
        print("Ejemplos:")
        print("  py asignar_tcs.py 1160899,1160900,1160901,1160902")
        print("  py asignar_tcs.py --hu 1129578")
        sys.exit(1)

    tcs_ids = []

    if sys.argv[1] == "--hu":
        if len(sys.argv) < 3:
            print("[ERROR] Falta el ID de la HU")
            sys.exit(1)
        hu_id = int(sys.argv[2])
        print(f"\n[INFO] Buscando contenedor 'Pruebas de calidad' de la HU #{hu_id}...")
        contenedor_id = buscar_contenedor_pruebas_calidad(hu_id)
        if not contenedor_id:
            print(f"[ERROR] No se encontro contenedor 'Pruebas de calidad' en la HU #{hu_id}")
            sys.exit(1)
        print(f"[OK] Contenedor: #{contenedor_id}")
        print(f"[INFO] Buscando TCs hijos...")
        tcs_ids = obtener_hijos_tcs(contenedor_id)
        if not tcs_ids:
            print(f"[INFO] El contenedor #{contenedor_id} no tiene TCs hijos.")
            sys.exit(0)
    else:
        # Lista de IDs separados por coma
        tcs_ids = [int(x.strip()) for x in sys.argv[1].split(",")]

    print(f"\n[INFO] {len(tcs_ids)} TC(s) a asignar a {ASSIGNED_TO_EMAIL}")
    print("=" * 70)

    for tc_id in tcs_ids:
        print(asignar_tc(tc_id))

    print("=" * 70)
    print("[FIN]")
