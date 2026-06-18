# -*- coding: utf-8 -*-
"""
crear_bug.py - Crea un Bug en Azure DevOps leyendo un Test Case existente.
Parte del toolkit qa-cli.

Uso:
    py crear_bug.py
    py crear_bug.py --tc 123456
    py crear_bug.py --tc 123456 --dry-run

Flujo:
    1. Pide el ID del TC fallido
    2. Lee el TC desde ADO (título + Gherkin + HT padre)
    3. Deriva automáticamente: descripción, datos de prueba, pasos, resultado esperado
    4. Pide al QA solo: desarrollador, qué falló (una línea), severidad y si es bloqueante
    5. Preview completo → confirmación → crea en ADO
    6. Registra en output/registro_bugs.csv
"""

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
CONFIG_PATH   = os.path.join(os.path.dirname(__file__), "config.json")
REGISTRO_PATH = os.path.join(os.path.dirname(__file__), "output", "registro_bugs.csv")

SEVERIDADES  = ["1. Crítica", "2. Media", "3. Baja"]
NIVELES      = ["Aceptación", "E2E", "Integración", "Sistema"]
ETAPAS       = ["Certificación", "Exploración", "Post-implantación", "Regresión"]

# ---------------------------------------------------------------------------
# Helpers ADO
# ---------------------------------------------------------------------------

def cargar_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] No se encontró config.json en {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def ado_headers(pat: str) -> dict:
    import base64
    token = base64.b64encode(f":{pat}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


def obtener_work_item(wi_id: int, cfg: dict, pat: str) -> dict:
    org, proj = cfg["organization"], cfg["project"]
    url = (f"https://dev.azure.com/{org}/{proj}/_apis/wit/workitems/{wi_id}"
           f"?$expand=relations&api-version=7.1")
    resp = requests.get(url, headers=ado_headers(pat))
    if resp.status_code != 200:
        print(f"[ERROR] No se pudo obtener WI #{wi_id}: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    return resp.json()


def obtener_padre(wi: dict):
    for rel in (wi.get("relations") or []):
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            m = re.search(r"/(\d+)$", rel.get("url", ""))
            if m:
                return int(m.group(1))
    return None

# ---------------------------------------------------------------------------
# Parsear Gherkin del TC → campos del bug
# ---------------------------------------------------------------------------

def html_encode(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def parsear_gherkin(gherkin_raw: str) -> dict:
    """
    Lee el Gherkin del TC y extrae:
      - scenario_title : línea Scenario/Feature
      - given_lines    : líneas Given/And después de Given  → Datos de prueba
      - when_lines     : líneas When/And después de When   → Pasos
      - then_lines     : líneas Then/And después de Then   → Resultado esperado
    """
    # Limpiar HTML que ADO mete en el campo Description
    texto = re.sub(r"<[^>]+>", "\n", gherkin_raw or "")
    texto = re.sub(r"&nbsp;", " ", texto)
    texto = re.sub(r"&lt;",   "<", texto)
    texto = re.sub(r"&gt;",   ">", texto)
    texto = re.sub(r"&amp;",  "&", texto)
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]

    scenario_title = ""
    given, when, then = [], [], []
    seccion = None

    for linea in lineas:
        low = linea.lower()
        if low.startswith("feature:") or low.startswith("scenario:") or low.startswith("scenario outline:"):
            scenario_title = re.split(r":", linea, maxsplit=1)[-1].strip()
            seccion = None
        elif low.startswith("given que") or low.startswith("given"):
            seccion = "given"
            given.append(linea)
        elif low.startswith("when") or low.startswith("cuando"):
            seccion = "when"
            when.append(linea)
        elif low.startswith("then") or low.startswith("entonces"):
            seccion = "then"
            then.append(linea)
        elif low.startswith("and") or low.startswith("y ") or low.startswith("pero"):
            if seccion == "given": given.append(linea)
            elif seccion == "when": when.append(linea)
            elif seccion == "then": then.append(linea)
        # líneas de datos (tablas, ejemplos)
        elif linea.startswith("|"):
            if seccion == "given": given.append(linea)
            elif seccion == "when": when.append(linea)

    return {
        "scenario_title": scenario_title,
        "given": given,
        "when":  when,
        "then":  then,
    }


def construir_campos_desde_tc(tc_titulo: str, gherkin_raw: str, fallo: str,
                               severidad: str, bloqueante: str,
                               nivel_prueba: str, etapa: str) -> dict:
    g = parsear_gherkin(gherkin_raw)

    # ── Título del bug ──────────────────────────────────────────────────────
    titulo = f"[BUG] {tc_titulo}"
    if len(titulo) > 120:
        titulo = titulo[:117] + "..."

    # ── Descripción ─────────────────────────────────────────────────────────
    # Descripción rica: comportamiento observado + escenario + resultado real vs esperado
    descripcion = f"<p><b>**Descripción:**</b> {html_encode(fallo)}</p>"
    if g["scenario_title"]:
        descripcion += f"<p><b>Escenario del TC:</b> {html_encode(g['scenario_title'])}</p>"
    if g["then"]:
        then_txt = " / ".join(g["then"][:3])
        descripcion += (
            f"<p><b>Resultado esperado:</b> {html_encode(then_txt)}</p>"
            f"<p><b>Resultado obtenido:</b> {html_encode(fallo)}</p>"
        )
    descripcion += f"<p><b>TC de referencia:</b> {html_encode(tc_titulo)}</p>"

    # ── Datos de prueba (Given) ──────────────────────────────────────────────
    if g["given"]:
        items = "".join(f"<li>{html_encode(l)}</li>" for l in g["given"])
        datos_prueba = f"<ul>{items}</ul>"
    else:
        datos_prueba = "<p>(Ver descripción del Test Case)</p>"

    # ── Pasos para reproducir (When) ────────────────────────────────────────
    if g["when"]:
        items = "".join(f"<li>{html_encode(l)}</li>" for l in g["when"])
        pasos = f"<ol>{items}</ol>"
    else:
        pasos = f"<ol><li>{html_encode(fallo)}</li></ol>"

    # ── Resultado esperado (Then) ────────────────────────────────────────────
    if g["then"]:
        items = "".join(f"<li>{html_encode(l)}</li>" for l in g["then"])
        resultado_esperado = f"<ul>{items}</ul>"
    else:
        resultado_esperado = "<p>(Ver criterios de aceptación del Test Case)</p>"

    # ── Causa raíz (inferida del fallo) ─────────────────────────────────────
    causa_raiz = fallo[:200]

    return {
        "titulo":              titulo,
        "descripcion":         descripcion,
        "datos_prueba":        datos_prueba,
        "pasos":               pasos,
        "resultado_esperado":  resultado_esperado,
        "severidad":           severidad,
        "bloqueante":          bloqueante,
        "atributo_calidad":    "Funcional",
        "nivel_prueba":        nivel_prueba,
        "etapa_descubrimiento":etapa,
        "causa_raiz":          causa_raiz,
    }

# ---------------------------------------------------------------------------
# Crear Bug en ADO
# ---------------------------------------------------------------------------

def crear_bug_ado(campos: dict, tc_id: int, ht_id, dev: str,
                  cfg: dict, pat: str,
                  area_path: str = "", iter_path: str = "") -> dict:
    org, proj = cfg["organization"], cfg["project"]
    url = f"https://dev.azure.com/{org}/{proj}/_apis/wit/workitems/$Bug?api-version=7.1"

    patch = [
        {"op": "add", "path": "/fields/System.AreaPath",                 "value": area_path},
        {"op": "add", "path": "/fields/System.IterationPath",            "value": iter_path},
        {"op": "add", "path": "/fields/System.Title",                   "value": campos["titulo"]},
        {"op": "add", "path": "/fields/System.Description",             "value": campos["descripcion"]},
        {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.ReproSteps",  "value": campos["pasos"]},
        {"op": "add", "path": "/fields/Custom.Datosdeprueba",           "value": campos["datos_prueba"]},
        {"op": "add", "path": "/fields/Microsoft.VSTS.Common.Severity", "value": campos["severidad"]},
        {"op": "add", "path": "/fields/Custom.Bloqueante",              "value": campos["bloqueante"]},
        {"op": "add", "path": "/fields/Custom.Atributodecalidad",       "value": campos["atributo_calidad"]},
        {"op": "add", "path": "/fields/Custom.Nivelprueba",           "value": campos["nivel_prueba"]},
        {"op": "add", "path": "/fields/Custom.Origen",                  "value": "Manual"},
        {"op": "add", "path": "/fields/Custom.Etapadedescubrimiento",   "value": campos["etapa_descubrimiento"]},
        {"op": "add", "path": "/fields/System.AssignedTo",              "value": dev},
        {"op": "add", "path": "/fields/Custom.9fcf5e7b-aac8-44a0-9476-653d3ea45e14", "value": campos.get("id_apm", "")},
    ]

    # Bug como hijo directo del TC
    patch.append({
        "op": "add", "path": "/relations/-",
        "value": {
            "rel": "System.LinkTypes.Hierarchy-Reverse",
            "url": f"https://dev.azure.com/{org}/_apis/wit/workitems/{tc_id}",
            "attributes": {"comment": f"Bug detectado en ejecución del TC #{tc_id}"}
        }
    })

    headers = ado_headers(pat)
    headers["Content-Type"] = "application/json-patch+json"
    resp = requests.patch(url, headers=headers, json=patch)
    if resp.status_code not in (200, 201):
        print(f"[ERROR] Al crear el bug: {resp.status_code}\n{resp.text[:400]}")
        sys.exit(1)
    return resp.json()

# ---------------------------------------------------------------------------
# Menú de selección numerada
# ---------------------------------------------------------------------------

def elegir(opciones: list, etiqueta: str) -> str:
    print(f"\n  {etiqueta}")
    for i, op in enumerate(opciones, 1):
        print(f"    {i}. {op}")
    while True:
        r = input("  Elige (número): ").strip()
        if r.isdigit() and 1 <= int(r) <= len(opciones):
            return opciones[int(r) - 1]
        print("  Opción inválida, intenta de nuevo.")

# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def plain(html: str, max_chars: int = 300) -> str:
    txt = re.sub(r"<[^>]+>", " ", html or "")
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:max_chars] + ("…" if len(txt) > max_chars else "")


def mostrar_preview(campos: dict, dev: str, tc_id: int, ht_id, dry_run: bool):
    tag = "  ⚠️  DRY-RUN — nada será creado en ADO" if dry_run else "  PREVIEW DEL BUG"
    print("\n" + "═" * 65)
    print(tag)
    print("═" * 65)
    print(f"  Título             : {campos['titulo']}")
    print(f"  Severidad          : {campos['severidad']}")
    print(f"  ¿Bloqueante?       : {campos['bloqueante']}")
    print(f"  Atributo calidad   : {campos['atributo_calidad']}")
    print(f"  Nivel prueba       : {campos['nivel_prueba']}")
    print(f"  Etapa descubrim.   : {campos['etapa_descubrimiento']}")
    print(f"  Causa raíz         : {campos['causa_raiz']}")
    print(f"  Asignado a         : {dev}")
    print(f"  TC fallido         : #{tc_id}")
    print(f"  HT padre           : #{ht_id}" if ht_id else "  HT padre           : (ninguna)")
    print("─" * 65)
    print(f"  Descripción        : {plain(campos['descripcion'])}")
    print(f"  Datos de prueba    : {plain(campos['datos_prueba'])}")
    print(f"  Pasos              : {plain(campos['pasos'])}")
    print(f"  Resultado esperado : {plain(campos['resultado_esperado'])}")
    print("═" * 65)

# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------

def registrar_bug(bug_id: int, titulo: str, tc_id: int, ht_id, dev: str):
    os.makedirs(os.path.dirname(REGISTRO_PATH), exist_ok=True)
    existe = os.path.exists(REGISTRO_PATH)
    with open(REGISTRO_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        if not existe:
            w.writerow(["Fecha", "BUG_ID", "Titulo", "TC_ID", "HT_ID", "Desarrollador"])
        w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"),
                    bug_id, titulo, tc_id, ht_id or "", dev])

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Crea un Bug en ADO desde un TC fallido.")
    parser.add_argument("--tc",      type=int, help="ID del Test Case fallido")
    parser.add_argument("--dev",     type=str, help="Email o nombre del desarrollador")
    parser.add_argument("--fallo",   type=str, help="Qué está fallando (una línea)")
    parser.add_argument("--id-apm",  type=str, default="", help="ID solución en APM")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview sin crear nada en ADO")
    args = parser.parse_args()

    cfg = cargar_config()
    pat = os.environ.get("AZURE_DEVOPS_PAT", "")
    if not pat:
        print("[ERROR] AZURE_DEVOPS_PAT no configurada.")
        sys.exit(1)

    dry_run = args.dry_run
    print("=" * 65)
    print("  🐞  CREAR BUG  —  qa-cli" + ("  [DRY-RUN]" if dry_run else ""))
    print("=" * 65)

    # 1. TC
    tc_id = args.tc
    if not tc_id:
        s = input("\n📋  ID del Test Case fallido: ").strip()
        if not s.isdigit():
            print("[ERROR] ID inválido."); sys.exit(1)
        tc_id = int(s)

    # 2. Leer TC desde ADO
    print(f"\n🔍  Leyendo TC #{tc_id} desde ADO...")
    tc_wi      = obtener_work_item(tc_id, cfg, pat)
    fields     = tc_wi.get("fields", {})
    tc_titulo  = fields.get("System.Title", "(sin título)")
    tc_gherkin = fields.get("System.Description", "(sin descripción)")
    tc_tipo    = fields.get("System.WorkItemType", "")

    # Tomar nivel de prueba y etapa desde config si existen
    nivel_default = cfg.get("default_nivel_prueba", "Integración")
    etapa_default = "Certificación"

    if tc_tipo not in ("Test Case", "Caso de prueba"):
        r = input(f"  ⚠️  Tipo '{tc_tipo}'. ¿Continuar? (s/n): ").strip().lower()
        if r != "s": sys.exit(0)

    print(f"  ✅  {tc_titulo[:80]}")

    # 3. HT padre
    ht_id = obtener_padre(tc_wi)
    if ht_id:
        ht_wi      = obtener_work_item(ht_id, cfg, pat)
        ht_titulo  = ht_wi.get("fields", {}).get("System.Title", "")
        area_path  = ht_wi.get("fields", {}).get("System.AreaPath", "")
        iter_path  = ht_wi.get("fields", {}).get("System.IterationPath", "")
        print(f"  🔗  HT padre: #{ht_id} — {ht_titulo[:70]}")
    else:
        area_path = cfg.get("organization", "")
        iter_path = ""
        print("  ⚠️   Sin HT padre.")

    # 4. Desarrollador
    dev = args.dev or input("\n👤  Email del desarrollador responsable (ej: darwin.meneses@sura.com.co): ").strip()
    if not dev:
        print("[ERROR] El desarrollador es requerido."); sys.exit(1)

    # 5. Qué está fallando
    fallo = args.fallo
    if not fallo:
        print("\n🐛  ¿Qué está fallando? (una línea basta):")
        fallo = input("   > ").strip()
    if not fallo:
        print("[ERROR] Debes indicar qué está fallando."); sys.exit(1)

    # 6. Severidad (menú)
    severidad = elegir(SEVERIDADES, "📊  Severidad del bug:")

    # 7. Bloqueante
    print("\n  🚧  ¿Es bloqueante?")
    print("    1. Sí")
    print("    2. No")
    bloqueante = "Sí" if input("  Elige (número): ").strip() == "1" else "No"

    # 8. Nivel de prueba (toma el del config por defecto, permite cambiar)
    print(f"\n  ℹ️   Nivel de prueba por defecto del config: {nivel_default}")
    cambiar = input("  ¿Cambiar? (s/n): ").strip().lower()
    nivel_prueba = elegir(NIVELES, "🔬  Nivel de prueba:") if cambiar == "s" else nivel_default

    # 9. Etapa de descubrimiento (Certificación por defecto)
    print(f"\n  ℹ️   Etapa de descubrimiento por defecto: {etapa_default}")
    cambiar = input("  ¿Cambiar? (s/n): ").strip().lower()
    etapa = elegir(ETAPAS, "📍  Etapa de descubrimiento:") if cambiar == "s" else etapa_default

    # 10. ID de la solución en el APM (requerido por ADO)
    id_apm = args.id_apm
    if not id_apm:
        id_apm = input("\n🔑  ID de la solución en el APM (requerido, ej: 895): ").strip()
    if not id_apm:
        print("[ERROR] El ID APM es requerido por ADO.")
        sys.exit(1)

    # 11. Construir campos desde el TC
    print("\n⚙️   Construyendo campos desde el Test Case...")
    campos = construir_campos_desde_tc(
        tc_titulo, tc_gherkin, fallo,
        severidad, bloqueante, nivel_prueba, etapa
    )
    campos["id_apm"] = id_apm

    # 12. Preview
    mostrar_preview(campos, dev, tc_id, ht_id, dry_run)

    if dry_run:
        print("\n  ✅  DRY-RUN completado. Sin cambios en ADO.")
        print("      Corre sin --dry-run para crear el bug real.\n")
        return

    # 13. Confirmar
    if input("\n¿Crear este bug en ADO? (s/n): ").strip().lower() != "s":
        print("[CANCELADO]"); sys.exit(0)

    # 14. Crear
    print("\n📤  Creando bug en ADO...")
    bug_wi  = crear_bug_ado(campos, tc_id, ht_id, dev, cfg, pat, area_path, iter_path)
    bug_id  = bug_wi["id"]
    bug_url = bug_wi.get("_links", {}).get("html", {}).get("href", "")

    print(f"\n  ✅  Bug creado: #{bug_id} — {campos['titulo']}")
    if bug_url:
        print(f"  🔗  {bug_url}")

    registrar_bug(bug_id, campos["titulo"], tc_id, ht_id, dev)
    print(f"  📄  Registrado en output/registro_bugs.csv")
    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
