"""
QA-CLI - Comando unico para automatizar la creacion de Test Cases en Azure DevOps

Uso:
    py qa-cli.py <ID_HU_o_HT>
    py qa-cli.py <ID1> <ID2> <ID3>...     (lote)

Ejemplos:
    py qa-cli.py 1129579
    py qa-cli.py 1129577 1129578 1129579

Flujo automatico:
    1. Lee la HU/HT de Azure DevOps
    2. Genera archivo WI_xxxx.md
    3. Copia contenido al portapapeles
    4. Abre VS Code y Copilot Chat
    5. Espera a que Copilot genere TCs_HU_xxxx.md
    6. Te muestra los TCs para revision
    7. Sube los TCs como hijos de la HU/HT (asignados a ti)
"""

import requests
import base64
import os
import sys
import re
import json
import time
import subprocess
import platform
import shutil
from datetime import datetime
from getpass import getpass

# ============================================================
# CONFIGURACION (lee desde config.json)
# ============================================================
def cargar_config():
    if not os.path.exists("config.json"):
        print("[ERROR] config.json no encontrado.")
        print("        Crea el archivo config.json con tu informacion de Sura.")
        sys.exit(1)
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


CONFIG = cargar_config()
ORG = CONFIG["organization"]
PROJ = CONFIG["project"]
USER_EMAIL = CONFIG["user_email"]
USER_NAME = CONFIG.get("user_name", USER_EMAIL)
MODULO = CONFIG.get("modulo_default", "")
MAX_TCS_HU = CONFIG.get("max_tcs_hu", 4)
MAX_TCS_HT = CONFIG.get("max_tcs_ht", 3)
DEFAULT_TIPO_EJECUCION = CONFIG.get("default_tipo_ejecucion", "Manual")
DEFAULT_FASE = CONFIG.get("default_fase", "Construcción")
DEFAULT_NIVEL_PRUEBA = CONFIG.get("default_nivel_prueba", "Integración")

# Carpeta base para archivos generados (configurable en config.json)
OUTPUT_BASE = CONFIG.get("output_dir", "output")


def carpeta_salida():
    """Devuelve (y crea si no existe) la carpeta de salida del dia: output/YYYY-MM-DD/"""
    carpeta = os.path.join(OUTPUT_BASE, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def archivar(*archivos):
    """Mueve los archivos generados (WI_x.md, TCs_HU_x.md) a output/<fecha>/.

    Se ejecuta al final de cada HU para mantener el root del workspace limpio.
    Copilot sigue escribiendo en el root (el polling depende de eso); aqui
    solo se archivan una vez termina el proceso.
    """
    destino = carpeta_salida()
    for archivo in archivos:
        if archivo and os.path.exists(archivo):
            destino_final = os.path.join(destino, os.path.basename(archivo))
            if os.path.exists(destino_final):
                os.remove(destino_final)
            shutil.move(archivo, destino_final)
            print(f"        Archivado: {destino_final}")


BASE = f"https://dev.azure.com/{ORG}"

CAMPO_TIPO_EJECUCION = "Custom.886da9bd-0220-4a21-b0c7-1d93ecdf4390"
CAMPO_PRIORIDAD_CASO = "Custom.Prioridaddecaso"
CAMPO_FASE = "Custom.Fase"
CAMPO_NIVEL_PRUEBA = "Custom.Niveldeprueba"

PRIORIDAD_MAP = {
    "alta": "1", "high": "1", "1": "1",
    "media": "2", "medium": "2", "2": "2",
    "baja": "3", "low": "3", "3": "3",
}

NORMALIZAR_FASE = {
    "construccion": "Construcción", "construcción": "Construcción",
    "estabilizacion": "Estabilización", "estabilización": "Estabilización",
    "produccion": "Producción", "producción": "Producción",
}

NORMALIZAR_NIVEL = {
    "unitaria": "Unitaria",
    "integracion": "Integración", "integración": "Integración",
    "e2e": "E2E",
    "regresion": "Regresión", "regresión": "Regresión",
    "humo": "Humo",
    "aceptacion": "Aceptación", "aceptación": "Aceptación",
}

NORMALIZAR_TIPO_EJECUCION = {
    "manual": "Manual",
    "automatizado": "Automatizado", "automatico": "Automatizado",
    "automático": "Automatizado", "automatizada": "Automatizado",
}

# ============================================================
# AUTENTICACION
# ============================================================
PAT = os.environ.get("AZURE_DEVOPS_PAT")
if not PAT:
    print("[INFO] No se encontro la variable AZURE_DEVOPS_PAT.")
    PAT = getpass("Pega tu PAT: ").strip()
if not PAT:
    print("[ERROR] PAT requerido.")
    sys.exit(1)


def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}


# ============================================================
# UTILIDADES
# ============================================================
def limpiar_html(html):
    if not html:
        return ""
    t = html
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'</p>', '\n', t, flags=re.I)
    t = re.sub(r'</div>', '\n', t, flags=re.I)
    t = re.sub(r'<li>', '\n- ', t, flags=re.I)
    t = re.sub(r'</li>', '', t, flags=re.I)
    t = re.sub(r'<h[1-6]>', '\n### ', t, flags=re.I)
    t = re.sub(r'</h[1-6]>', '\n', t, flags=re.I)
    t = re.sub(r'<strong>(.*?)</strong>', r'**\1**', t, flags=re.I | re.DOTALL)
    t = re.sub(r'<b>(.*?)</b>', r'**\1**', t, flags=re.I | re.DOTALL)
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<')
    t = t.replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'")
    t = re.sub(r'\n\s*\n', '\n\n', t)
    return t.strip()


def gherkin_a_html(texto):
    if not texto:
        return ""
    html = []
    for linea in texto.strip().split("\n"):
        esc = linea.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        leading = len(linea) - len(linea.lstrip())
        if leading > 0:
            esc = "&nbsp;" * leading + esc.lstrip()
        html.append(f"<div>{esc}</div>" if esc else "<div>&nbsp;</div>")
    return "".join(html)


def copiar_al_portapapeles(texto):
    """Copia texto al portapapeles (Windows)."""
    try:
        if platform.system() == "Windows":
            subprocess.run(["clip"], input=texto, text=True, encoding="utf-8", check=True)
            return True
    except Exception as e:
        print(f"[WARN] No se pudo copiar al portapapeles: {e}")
    return False


# ============================================================
# AZURE DEVOPS - LECTURA
# ============================================================
def obtener_wi(wid, expand_relations=False):
    expand = "&$expand=relations" if expand_relations else ""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{wid}?api-version=7.1{expand}"
    r = requests.get(url, headers=h_json(), timeout=15)
    return r.json() if r.status_code == 200 else None


def wi_a_markdown(wi):
    """Genera el markdown completo de un work item."""
    f = wi.get("fields", {})
    wid = wi.get("id")
    tipo = f.get("System.WorkItemType", "")
    titulo = f.get("System.Title", "")
    estado = f.get("System.State", "")
    desc = limpiar_html(f.get("System.Description", ""))
    crit = limpiar_html(f.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))

    md = []
    md.append(f"# {tipo} #{wid} - {titulo}")
    md.append("")
    md.append(f"_Extraido el {datetime.now().strftime('%d/%m/%Y %H:%M')}_")
    md.append("")
    md.append(f"**Tipo:** {tipo}  |  **Estado:** {estado}")
    md.append("")
    md.append(f"**URL:** {BASE}/{PROJ}/_workitems/edit/{wid}")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## Descripcion")
    md.append("")
    md.append(desc if desc else "_(sin descripcion)_")
    md.append("")
    if crit:
        md.append("## Criterios de Aceptacion")
        md.append("")
        md.append(crit)
        md.append("")
    return "\n".join(md)


# ============================================================
# PARSEO Y SUBIDA DE TCs
# ============================================================
def parsear_tcs(ruta_md):
    if not os.path.exists(ruta_md):
        return []
    with open(ruta_md, "r", encoding="utf-8") as f:
        contenido = f.read()

    bloques = re.findall(r'#{2,3}\s*TC[^\n]*\n([\s\S]*?)(?=#{2,3}\s*TC|\Z)', contenido)
    if not bloques:
        bloques = re.split(r'\n---+\n', contenido)
        bloques = [b for b in bloques if "Feature:" in b and "Scenario:" in b]

    tcs = []
    for bloque in bloques:
        tc = parsear_bloque(bloque)
        if tc:
            tcs.append(tc)
    return tcs


def parsear_bloque(bloque):
    tc = {
        "title": "", "gherkin": "",
        "tipo_ejecucion": DEFAULT_TIPO_EJECUCION,
        "fase": DEFAULT_FASE,
        "nivel_prueba": DEFAULT_NIVEL_PRUEBA,
        "prioridad": "2",
    }
    m = re.search(r'\*\*Title[^:]*:\*\*\s*\n?\s*([^\n*]+)', bloque, re.I)
    if m:
        tc["title"] = m.group(1).strip()

    m = re.search(r'```(?:gherkin)?\s*\n(Feature:[\s\S]*?)```', bloque, re.I)
    if m:
        tc["gherkin"] = m.group(1).strip()
    if not tc["gherkin"]:
        m = re.search(r'(Feature:[\s\S]*?)(?=\n\*\*|\n#|\n---|\Z)', bloque)
        if m:
            tc["gherkin"] = m.group(1).strip()

    m = re.search(r'Tipo de ejecuci[oó]n:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["tipo_ejecucion"] = NORMALIZAR_TIPO_EJECUCION.get(m.group(1).strip().lower(), DEFAULT_TIPO_EJECUCION)

    m = re.search(r'Fase:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["fase"] = NORMALIZAR_FASE.get(m.group(1).strip().lower(), DEFAULT_FASE)

    m = re.search(r'Nivel de prueba:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["nivel_prueba"] = NORMALIZAR_NIVEL.get(m.group(1).strip().lower(), DEFAULT_NIVEL_PRUEBA)

    m = re.search(r'Prioridad(?:\s+de\s+caso)?:?\s*([^\n,]+)', bloque, re.I)
    if m:
        tc["prioridad"] = PRIORIDAD_MAP.get(m.group(1).strip().lower(), "2")

    if tc["title"] and tc["gherkin"]:
        return tc
    return None


def crear_tc(tc, padre_id, area_path, iteration_path):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/$Caso%20de%20prueba?api-version=7.1"
    desc_html = gherkin_a_html(tc["gherkin"])

    ops = [
        {"op": "add", "path": "/fields/System.Title", "value": tc["title"]},
        {"op": "add", "path": "/fields/System.Description", "value": desc_html},
        {"op": "add", "path": "/fields/System.AreaPath", "value": area_path},
        {"op": "add", "path": "/fields/System.IterationPath", "value": iteration_path},
        {"op": "add", "path": "/fields/System.AssignedTo", "value": USER_EMAIL},
        {"op": "add", "path": f"/fields/{CAMPO_TIPO_EJECUCION}", "value": tc["tipo_ejecucion"]},
        {"op": "add", "path": f"/fields/{CAMPO_FASE}", "value": tc["fase"]},
        {"op": "add", "path": f"/fields/{CAMPO_NIVEL_PRUEBA}", "value": tc["nivel_prueba"]},
        {"op": "add", "path": f"/fields/{CAMPO_PRIORIDAD_CASO}", "value": tc["prioridad"]},
        {"op": "add", "path": "/relations/-", "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"{BASE}/{PROJ}/_apis/wit/workItems/{padre_id}",
        }}
    ]

    r = requests.post(url, headers=h_patch(), json=ops, timeout=20)
    if r.status_code in (200, 201):
        return r.json().get("id"), None
    return None, f"Status {r.status_code}: {r.text[:300]}"


# ============================================================
# FLUJO PRINCIPAL POR HU
# ============================================================
def procesar_hu(hu_id, idx=None, total=None):
    prefix = f"[{idx}/{total}] " if idx else ""
    print(f"\n{'=' * 70}")
    print(f"{prefix}PROCESANDO HU #{hu_id}")
    print('=' * 70)

    # Paso 1: Leer HU
    print(f"\n  [1/4] Descargando HU #{hu_id}...")
    wi = obtener_wi(hu_id)
    if not wi:
        print(f"  [ERROR] No se pudo obtener la HU #{hu_id}")
        return False

    fields = wi.get("fields", {})
    tipo = fields.get("System.WorkItemType", "")
    titulo = fields.get("System.Title", "")
    area = fields.get("System.AreaPath", "")
    iteracion = fields.get("System.IterationPath", "")

    if tipo not in ("Historia", "User Story", "Product Backlog Item",
                    "Historia tecnica", "Historia técnica"):
        print(f"  [ERROR] Tipo no soportado: {tipo} (debe ser HU o HT)")
        return False

    max_tcs = MAX_TCS_HU if tipo in ("Historia", "User Story", "Product Backlog Item") else MAX_TCS_HT

    print(f"        OK - {tipo}: {titulo[:60]}")

    # Paso 2: Generar archivo .md de la HU
    archivo_hu = f"WI_{hu_id}.md"
    archivo_tcs = f"TCs_HU_{hu_id}.md"

    md_hu = wi_a_markdown(wi)
    with open(archivo_hu, "w", encoding="utf-8") as f:
        f.write(md_hu)
    print(f"  [2/4] Archivo generado: {archivo_hu}")

    # Borrar archivo TCs si existe (para detectar cuando Copilot lo crea)
    if os.path.exists(archivo_tcs):
        os.remove(archivo_tcs)

    # Crear el prompt para Copilot
    prompt = f"""Lee .github/copilot-instructions.md y genera los Test Cases para la siguiente {tipo}.

REGLA CRITICA: MAXIMO {max_tcs} TCs (es una {tipo}).

Sigue ESTRICTAMENTE el formato Sura:
- Title en ESPAÑOL descriptivo
- Description con Feature + Scenario + Steps en Gherkin (keywords ingles, contenido español)
- Campos custom: Tipo ejecucion={DEFAULT_TIPO_EJECUCION}, Fase={DEFAULT_FASE}, Nivel prueba={DEFAULT_NIVEL_PRUEBA}

IMPORTANTE: Al terminar, GUARDA TODOS los TCs en un archivo nuevo llamado "{archivo_tcs}" en el workspace.

{tipo} A PROCESAR:
=================

{md_hu}
"""

    # Copiar prompt al portapapeles
    if copiar_al_portapapeles(prompt):
        print(f"        OK - Prompt copiado al portapapeles")
    else:
        print(f"        [WARN] No se pudo copiar al portapapeles, copia manual desde {archivo_hu}")

    # Abrir VS Code con el archivo
    try:
        subprocess.Popen(["code", archivo_hu], shell=True)
    except Exception:
        pass

    # Paso 3: Esperar a que Copilot genere los TCs
    print()
    print("  +" + "=" * 66 + "+")
    print("  | AHORA TE TOCA A TI:                                              |")
    print("  |                                                                  |")
    print("  | 1. Abre Copilot Chat (Ctrl+Alt+I)                                |")
    print("  | 2. Click en '+ New Chat' (chat nuevo)                            |")
    print(f"  | 3. PEGA con Ctrl+V (el prompt ya esta en tu portapapeles)        |")
    print(f"  | 4. Dale Enter y espera a que genere {archivo_tcs:<25}      |")
    print("  |                                                                  |")
    print("  | Esperando que el archivo aparezca...                             |")
    print("  +" + "=" * 66 + "+")
    print()

    # Polling: esperar a que el archivo exista y tenga contenido
    timeout = 600  # 10 minutos max
    start = time.time()
    spinner = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    i = 0
    ultimo_tamano = 0
    estable_desde = None

    while time.time() - start < timeout:
        if os.path.exists(archivo_tcs):
            tamano = os.path.getsize(archivo_tcs)
            if tamano > 200:  # archivo con contenido sustancial
                # Esperar que sea estable (Copilot termino de escribir)
                if tamano == ultimo_tamano:
                    if estable_desde is None:
                        estable_desde = time.time()
                    elif time.time() - estable_desde >= 3:
                        # Archivo estable por 3 segundos, asumimos que termino
                        print(f"\n  [3/4] [OK] Archivo {archivo_tcs} detectado y estable")
                        break
                else:
                    ultimo_tamano = tamano
                    estable_desde = None

        sys.stdout.write(f"\r  {spinner[i % len(spinner)]} Esperando archivo {archivo_tcs}... ")
        sys.stdout.flush()
        i += 1
        time.sleep(0.5)
    else:
        print(f"\n  [TIMEOUT] No se detecto {archivo_tcs} en 10 minutos.")
        resp = input("  Ya esta el archivo listo? Presiona ENTER para continuar o 'n' para cancelar: ").strip().lower()
        if resp == "n":
            return False

    # Paso 4: Revisar y subir
    tcs = parsear_tcs(archivo_tcs)
    if not tcs:
        print(f"  [ERROR] No se detectaron TCs en {archivo_tcs}")
        return False

    print(f"\n  [3/4] {len(tcs)} TC(s) detectados:")
    for i, tc in enumerate(tcs, 1):
        print(f"        {i}. {tc['title'][:65]}")

    # Confirmacion antes de subir
    print()
    resp = input(f"  Subir estos {len(tcs)} TCs como hijos directos de la {tipo} #{hu_id}? (s/n): ").strip().lower()
    if resp != "s":
        print("  [CANCELADO]")
        return False

    # Crear los TCs
    print(f"\n  [4/4] Creando TCs en Azure DevOps...")
    creados = []
    errores = []
    for i, tc in enumerate(tcs, 1):
        wid, error = crear_tc(tc, hu_id, area, iteracion)
        if wid:
            print(f"        [OK] #{wid}: {tc['title'][:55]}")
            creados.append(wid)
        else:
            print(f"        [ERROR] {tc['title'][:55]}")
            print(f"               {error[:100]}")
            errores.append((tc['title'], error))

    # Resumen
    print()
    print("  +" + "=" * 66 + "+")
    print(f"  | RESUMEN HU #{hu_id}: {len(creados)}/{len(tcs)} TCs creados".ljust(67) + " |")
    if errores:
        print(f"  | {len(errores)} errores".ljust(67) + " |")
    print("  +" + "=" * 66 + "+")
    print(f"  Ver: {BASE}/{PROJ}/_workitems/edit/{hu_id}")

    return len(creados) > 0


# ============================================================
# MAIN
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("\nUso: py qa-cli.py <ID_HU> [<ID2> <ID3> ...]")
        print("")
        print("Ejemplos:")
        print("  py qa-cli.py 1129579                       (una HU)")
        print("  py qa-cli.py 1129577 1129578 1129579       (lote)")
        sys.exit(1)

    ids = []
    for arg in sys.argv[1:]:
        if arg.isdigit():
            ids.append(int(arg))
        else:
            print(f"[WARN] Ignorando argumento no numerico: {arg}")

    if not ids:
        print("[ERROR] No se proporcionaron IDs validos.")
        sys.exit(1)

    print()
    print("#" * 70)
    print(f"#  QA-CLI - Procesamiento de {len(ids)} item(s)")
    print(f"#  Usuario: {USER_NAME} ({USER_EMAIL})")
    print("#" * 70)

    total_creados = 0
    fallidos = []
    inicio = time.time()

    for i, hu_id in enumerate(ids, 1):
        try:
            ok = procesar_hu(hu_id, i, len(ids))
            if not ok:
                fallidos.append(hu_id)
        except KeyboardInterrupt:
            print("\n[INTERRUMPIDO POR USUARIO]")
            sys.exit(0)
        except Exception as e:
            print(f"[ERROR] HU #{hu_id}: {e}")
            fallidos.append(hu_id)
        finally:
            # Archivar los .md generados para mantener el root limpio
            archivar(f"WI_{hu_id}.md", f"TCs_HU_{hu_id}.md")

    # Resumen global
    duracion = int(time.time() - inicio)
    mins = duracion // 60
    secs = duracion % 60

    print()
    print("#" * 70)
    print(f"#  PROCESO COMPLETO")
    print(f"#  HUs procesadas: {len(ids) - len(fallidos)}/{len(ids)}")
    print(f"#  Tiempo total: {mins}m {secs}s")
    if fallidos:
        print(f"#  HUs con errores: {fallidos}")
    print("#" * 70)


if __name__ == "__main__":
    main()