"""
Script para subir Test Cases automaticamente a Azure DevOps.

Lee un archivo .md con TCs generados por Copilot y los crea como hijos
del Caso de Prueba contenedor (ej: "Pruebas de calidad").

Uso:
    py subir_tcs.py <ID_CONTENEDOR> <archivo.md>

Ejemplo:
    py subir_tcs.py 1129661 TCs_HU_1129575.md
"""

import requests
import base64
import os
import sys
import re
import json
from getpass import getpass

ORGANIZATION = "SuraColombia"
PROJECT = "Gerencia_Tecnologia"
BASE_URL = f"https://dev.azure.com/{ORGANIZATION}"

# Nombres internos de campos custom (descubiertos con descubrir_campos.py)
# Asignar TCs creados a este usuario (cambiar si lo usa otra persona)
ASSIGNED_TO_EMAIL = "afcontreras@sura.com.co"

CAMPO_TIPO_EJECUCION = "Custom.886da9bd-0220-4a21-b0c7-1d93ecdf4390"
CAMPO_PRIORIDAD_CASO = "Custom.Prioridaddecaso"
CAMPO_FASE = "Custom.Fase"
CAMPO_NIVEL_PRUEBA = "Custom.Niveldeprueba"

# Mapeo de prioridad texto -> numero

# Diccionarios de normalizacion (Azure DevOps requiere valores EXACTOS con acentos)
NORMALIZAR_FASE = {
    "construccion": "Construcción",
    "construcción": "Construcción",
    "estabilizacion": "Estabilización",
    "estabilización": "Estabilización",
    "produccion": "Producción",
    "producción": "Producción",
}

NORMALIZAR_NIVEL = {
    "unitaria": "Unitaria",
    "integracion": "Integración",
    "integración": "Integración",
    "e2e": "E2E",
    "regresion": "Regresión",
    "regresión": "Regresión",
    "humo": "Humo",
    "aceptacion": "Aceptación",
    "aceptación": "Aceptación",
}

NORMALIZAR_TIPO_EJECUCION = {
    "manual": "Manual",
    "automatizado": "Automatizado",
    "automatico": "Automatizado",
    "automático": "Automatizado",
    "automatizada": "Automatizado",
}


def normalizar_valor(valor, mapa, default):
    """Normaliza un valor usando un mapa, o retorna default si no esta."""
    if not valor:
        return default
    clave = valor.strip().lower()
    return mapa.get(clave, default)

PRIORIDAD_MAP = {
    "alta": "1", "high": "1", "1": "1",
    "media": "2", "medium": "2", "2": "2",
    "baja": "3", "low": "3", "3": "3",
    "muy baja": "4", "4": "4",
}

PAT = os.environ.get("AZURE_DEVOPS_PAT")
if not PAT:
    PAT = getpass("PAT: ").strip()
if not PAT:
    sys.exit(1)


def headers_json():
    """Headers para llamadas JSON normales."""
    token = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def headers_patch():
    """Headers para crear/actualizar work items (necesita json-patch)."""
    token = base64.b64encode(f":{PAT}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json-patch+json"
    }


def gherkin_a_html(texto_gherkin):
    """Convierte el Gherkin plano a HTML para Azure DevOps."""
    if not texto_gherkin:
        return ""
    # Limpiar y dividir en lineas
    lineas = texto_gherkin.strip().split("\n")
    html_lineas = []
    for linea in lineas:
        # Escapar caracteres HTML basicos
        linea_html = linea.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Preservar indentacion con &nbsp;
        leading = len(linea) - len(linea.lstrip())
        if leading > 0:
            linea_html = "&nbsp;" * leading + linea_html.lstrip()
        html_lineas.append(f"<div>{linea_html}</div>" if linea_html else "<div>&nbsp;</div>")
    return "".join(html_lineas)


def obtener_workitem(wi_id, expand_relations=False):
    """Obtiene info de un work item."""
    expand = "&$expand=relations" if expand_relations else ""
    url = f"{BASE_URL}/{PROJECT}/_apis/wit/workitems/{wi_id}?api-version=7.1{expand}"
    r = requests.get(url, headers=headers_json(), timeout=15)
    if r.status_code != 200:
        return None
    return r.json()


def buscar_contenedor_pruebas_calidad(hu_id):
    """
    Busca el hijo 'Pruebas de calidad' (Caso de prueba contenedor) de una HU.
    Si encuentra solo uno, lo retorna automaticamente.
    Si encuentra varios, los muestra para que el usuario elija.
    """
    hu = obtener_workitem(hu_id, expand_relations=True)
    if not hu:
        return None

    relaciones = hu.get("relations", [])
    hijos_ids = []
    for rel in relaciones:
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Forward":
            hijo_id = int(rel["url"].split("/")[-1])
            hijos_ids.append(hijo_id)

    if not hijos_ids:
        return None

    # Obtener detalles de los hijos
    ids_str = ",".join(str(i) for i in hijos_ids)
    url = (f"{BASE_URL}/{PROJECT}/_apis/wit/workitems?ids={ids_str}"
           f"&fields=System.Id,System.Title,System.WorkItemType&api-version=7.1")
    r = requests.get(url, headers=headers_json(), timeout=15)
    if r.status_code != 200:
        return None

    hijos = r.json().get("value", [])

    # Filtrar solo Casos de prueba contenedores (que tengan "Pruebas de calidad" en el titulo)
    contenedores = []
    for h_item in hijos:
        f = h_item.get("fields", {})
        if f.get("System.WorkItemType") == "Caso de prueba":
            titulo = f.get("System.Title", "")
            if "pruebas de calidad" in titulo.lower():
                contenedores.append({
                    "id": h_item.get("id"),
                    "title": titulo
                })

    # Si no hay con "Pruebas de calidad", tomar cualquier Caso de prueba hijo
    if not contenedores:
        for h_item in hijos:
            f = h_item.get("fields", {})
            if f.get("System.WorkItemType") == "Caso de prueba":
                contenedores.append({
                    "id": h_item.get("id"),
                    "title": f.get("System.Title", "")
                })

    if not contenedores:
        return None

    # Si hay solo uno, retornarlo
    if len(contenedores) == 1:
        return contenedores[0]["id"]

    # Si hay varios, mostrar y dejar elegir
    print(f"\n[INFO] Encontre {len(contenedores)} posibles contenedores en la HU #{hu_id}:")
    for i, c in enumerate(contenedores, 1):
        print(f"  {i}. #{c['id']} - {c['title']}")

    while True:
        opcion = input(f"\nElige el numero del contenedor (1-{len(contenedores)}) o 'c' para cancelar: ").strip()
        if opcion.lower() == "c":
            return None
        if opcion.isdigit():
            idx = int(opcion) - 1
            if 0 <= idx < len(contenedores):
                return contenedores[idx]["id"]
        print("[ERROR] Opcion invalida.")


def resolver_contenedor(input_id):
    """
    Resuelve el padre directo de los TCs:
    - Los TCs van DIRECTO como hijos de la HU/HT (NO del 'Pruebas de calidad')
    - Si pasan un Caso de prueba, advertir que normalmente debe ser una HU/HT
    Retorna el work item padre o None.
    """
    wi = obtener_workitem(input_id)
    if not wi:
        return None

    tipo = wi.get("fields", {}).get("System.WorkItemType", "")
    titulo = wi.get("fields", {}).get("System.Title", "")

    # Caso normal: HU o HT - los TCs cuelgan directo de aqui
    if tipo in ("Historia", "User Story", "Product Backlog Item",
                "Historia tecnica", "Historia técnica"):
        print(f"[OK] ID {input_id} es una {tipo}: '{titulo}'")
        print(f"[INFO] Los TCs quedaran como hijos DIRECTOS de esta {tipo}")
        return wi

    # Si pasan un Caso de prueba, preguntar (puede ser intencional o un error)
    if tipo == "Caso de prueba":
        print(f"[WARN] ID {input_id} es un Caso de prueba: '{titulo}'")
        print(f"       Normalmente los TCs deben colgar de la HU/HT, no de otro TC.")
        resp = input(f"       Quieres usar este Caso de prueba como padre igual? (s/n): ").strip().lower()
        if resp == "s":
            return wi
        else:
            print(f"[INFO] Cancelado. Pasa el ID de la HU/HT directamente.")
            return None

    # Otro tipo no soportado
    print(f"[ERROR] Tipo no soportado: {tipo}. Debes pasar un ID de HU/HT.")
    return None


def obtener_contenedor(contenedor_id):
    """Mantenido para compatibilidad: ahora usa resolver_contenedor()."""
    return resolver_contenedor(contenedor_id)


def parsear_archivo_md(ruta):
    """Parsea el archivo .md y extrae cada TC."""
    if not os.path.exists(ruta):
        print(f"[ERROR] Archivo no encontrado: {ruta}")
        return []

    with open(ruta, "r", encoding="utf-8") as f:
        contenido = f.read()

    tcs = []

    # Patron para detectar bloques de TC
    # Buscamos secciones que comiencen con "### TC" o "## TC" hasta el proximo TC o final
    patron_tc = r'#{2,3}\s*TC[^\n]*\n([\s\S]*?)(?=#{2,3}\s*TC|\Z)'
    bloques = re.findall(patron_tc, contenido)

    # Si no encontro con ese patron, intentamos otro
    if not bloques:
        # Intento alternativo: buscar bloques separados por ---
        bloques = re.split(r'\n---+\n', contenido)
        bloques = [b for b in bloques if "Feature:" in b and "Scenario:" in b]

    for bloque in bloques:
        tc = parsear_bloque_tc(bloque)
        if tc:
            tcs.append(tc)

    return tcs


def parsear_bloque_tc(bloque):
    """Extrae datos de UN bloque de TC."""
    tc = {
        "title": "",
        "gherkin": "",
        "tipo_ejecucion": "Manual",
        "fase": "Construcción",
        "nivel_prueba": "Integración",
        "prioridad": "2",
        "modulo": "",
    }

    # Title
    m = re.search(r'\*\*Title[^:]*:\*\*\s*\n?\s*([^\n*]+)', bloque, re.I)
    if m:
        tc["title"] = m.group(1).strip()

    # Gherkin: buscar entre ```...``` o ``` gherkin
    m = re.search(r'```(?:gherkin)?\s*\n(Feature:[\s\S]*?)```', bloque, re.I)
    if m:
        tc["gherkin"] = m.group(1).strip()

    # Si no hay backticks, buscar Feature: ... hasta linea vacia doble o siguiente seccion
    if not tc["gherkin"]:
        m = re.search(r'(Feature:[\s\S]*?)(?=\n\*\*|\n#|\n---|\Z)', bloque)
        if m:
            tc["gherkin"] = m.group(1).strip()

    # Tipo de ejecucion
    m = re.search(r'Tipo de ejecuci[oó]n:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["tipo_ejecucion"] = normalizar_valor(m.group(1), NORMALIZAR_TIPO_EJECUCION, "Manual")

    # Fase
    m = re.search(r'Fase:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["fase"] = normalizar_valor(m.group(1), NORMALIZAR_FASE, "Construcción")

    # Nivel de prueba
    m = re.search(r'Nivel de prueba:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["nivel_prueba"] = normalizar_valor(m.group(1), NORMALIZAR_NIVEL, "Integración")

    # Prioridad
    m = re.search(r'Prioridad(?:\s+de\s+caso)?:?\s*([^\n,]+)', bloque, re.I)
    if m:
        prio_texto = m.group(1).strip().lower()
        tc["prioridad"] = PRIORIDAD_MAP.get(prio_texto, "2")

    # Modulo
    m = re.search(r'(?:Module|M[oó]dulo)[^:]*:?\s*([^\n]+)', bloque, re.I)
    if m:
        tc["modulo"] = m.group(1).strip()

    # Solo retornar si tiene al menos title y gherkin
    if tc["title"] and tc["gherkin"]:
        return tc
    return None


def crear_tc(tc, contenedor_id, area_path, iteration_path):
    """Crea un Caso de Prueba en Azure DevOps vinculado como hijo del contenedor."""
    url = (f"{BASE_URL}/{PROJECT}/_apis/wit/workitems/$Caso%20de%20prueba"
           f"?api-version=7.1")

    description_html = gherkin_a_html(tc["gherkin"])

    operaciones = [
        {"op": "add", "path": "/fields/System.Title", "value": tc["title"]},
        {"op": "add", "path": "/fields/System.Description", "value": description_html},
        {"op": "add", "path": "/fields/System.AreaPath", "value": area_path},
        {"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path},
        {"op": "add", "path": "/fields/System.AssignedTo", "value": ASSIGNED_TO_EMAIL},
        {"op": "add", "path": f"/fields/{CAMPO_TIPO_EJECUCION}", "value": tc["tipo_ejecucion"]},
        {"op": "add", "path": f"/fields/{CAMPO_FASE}", "value": tc["fase"]},
        {"op": "add", "path": f"/fields/{CAMPO_NIVEL_PRUEBA}", "value": tc["nivel_prueba"]},
        {"op": "add", "path": f"/fields/{CAMPO_PRIORIDAD_CASO}", "value": tc["prioridad"]},
        # Vinculacion: este TC es hijo del contenedor
        {
            "op": "add",
            "path": "/relations/-",
            "value": {
                "rel": "System.LinkTypes.Hierarchy-Reverse",
                "url": f"{BASE_URL}/{PROJECT}/_apis/wit/workItems/{contenedor_id}",
                "attributes": {"comment": "Hijo del contenedor de pruebas"}
            }
        }
    ]

    r = requests.post(url, headers=headers_patch(), json=operaciones, timeout=20)

    if r.status_code in (200, 201):
        data = r.json()
        return data.get("id"), None
    else:
        return None, f"Status {r.status_code}: {r.text[:300]}"


# ============================================================
# MAIN
# ============================================================
def main():
    if len(sys.argv) < 3:
        print("\nUso: py subir_tcs.py <ID_HU_o_HT> <archivo.md>")
        print("")
        print("Los TCs se crearan como hijos DIRECTOS de la HU/HT.")
        print("")
        print("Ejemplos:")
        print("  py subir_tcs.py 1129577 TCs_HU_1129577.md   (HU)")
        print("  py subir_tcs.py 1129580 TCs_HT_1129580.md   (HT)")
        sys.exit(1)

    try:
        contenedor_id = int(sys.argv[1])
    except ValueError:
        print("[ERROR] El ID del contenedor debe ser numerico.")
        sys.exit(1)

    archivo_md = sys.argv[2]

    # 1. Obtener info del contenedor (para heredar area y iteration)
    print(f"\n[INFO] Consultando contenedor #{contenedor_id}...")
    contenedor = obtener_contenedor(contenedor_id)
    if not contenedor:
        print(f"[ERROR] No se pudo obtener el contenedor #{contenedor_id}")
        sys.exit(1)

    fields_c = contenedor.get("fields", {})
    titulo_c = fields_c.get("System.Title", "")
    tipo_c = fields_c.get("System.WorkItemType", "")
    area_path = fields_c.get("System.AreaPath", "")
    iteration_path = fields_c.get("System.IterationPath", "")

    # CRITICO: usar el ID REAL del contenedor (puede haber sido resuelto desde una HU)
    contenedor_id = contenedor.get("id")
    print(f"[OK] Contenedor: {tipo_c} #{contenedor_id} - {titulo_c}")
    print(f"     Area: {area_path}")
    print(f"     Iteration: {iteration_path}")

    # 2. Parsear el archivo .md
    print(f"\n[INFO] Parseando archivo: {archivo_md}")
    tcs = parsear_archivo_md(archivo_md)

    if not tcs:
        print("[ERROR] No se encontraron TCs en el archivo.")
        print("        Verifica que el archivo tenga bloques con Title, Feature, Scenario, etc.")
        sys.exit(1)

    print(f"[OK] {len(tcs)} TCs detectados en el archivo:")
    for i, tc in enumerate(tcs, 1):
        print(f"     {i}. {tc['title'][:70]}")

    # 3. Confirmar antes de subir
    print()
    resp = input(f"Subir estos {len(tcs)} TCs como hijos del contenedor #{contenedor_id}? (s/n): ").strip().lower()
    if resp != "s":
        print("[CANCELADO]")
        sys.exit(0)

    # 4. Crear cada TC
    print("\n" + "=" * 70)
    print("CREANDO TEST CASES")
    print("=" * 70)

    ids_creados = []
    errores = []

    for i, tc in enumerate(tcs, 1):
        print(f"\n[{i}/{len(tcs)}] {tc['title'][:60]}...")
        wid, error = crear_tc(tc, contenedor_id, area_path, iteration_path)
        if wid:
            print(f"   [OK] Creado: #{wid}")
            print(f"        URL: {BASE_URL}/{PROJECT}/_workitems/edit/{wid}")
            ids_creados.append((wid, tc["title"]))
        else:
            print(f"   [ERROR] {error}")
            errores.append((tc["title"], error))

    # 5. Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print(f"  TCs creados exitosamente: {len(ids_creados)}/{len(tcs)}")

    if ids_creados:
        print(f"\n  IDs creados (hijos de #{contenedor_id}):")
        for wid, titulo in ids_creados:
            print(f"    - #{wid}: {titulo[:60]}")

    if errores:
        print(f"\n  Errores ({len(errores)}):")
        for titulo, err in errores:
            print(f"    - {titulo[:60]}")
            print(f"      {err[:200]}")

    print(f"\n  Ver en Azure DevOps:")
    print(f"  {BASE_URL}/{PROJECT}/_workitems/edit/{contenedor_id}")


if __name__ == "__main__":
    main()
