"""
Auditoria de Test Cases - Para entender el terreno antes de automatizar.

Lee los TCs hijos de una o varias HUs/HTs y genera un reporte ejecutivo
con el diagnostico de:
- Cantidad de TCs por padre
- Quien los creo
- Estado de cada TC
- Si el Gherkin esta estructurado
- Si menciona endpoints / metodos HTTP / status codes
- Recomendaciones

Uso:
    py auditar_tcs.py <ID1> [<ID2> <ID3> ...]
    py auditar_tcs.py 1083516 1083517 1083518 1083519 1083520 1083521
"""

import requests
import base64
import os
import sys
import re
import json
from datetime import datetime
from pathlib import Path
from collections import Counter
from getpass import getpass

# ============================================================
# CONFIG
# ============================================================
def cargar_config():
    if not os.path.exists("config.json"):
        return {"organization": "SuraColombia", "project": "Gerencia_Tecnologia"}
    with open("config.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)

CONFIG = cargar_config()
ORG = CONFIG.get("organization", "SuraColombia")
PROJ = CONFIG.get("project", "Gerencia_Tecnologia")
BASE = f"https://dev.azure.com/{ORG}"

PAT = os.environ.get("AZURE_DEVOPS_PAT") or getpass("PAT: ").strip()
if not PAT:
    sys.exit(1)


def h():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}


# ============================================================
# AZURE DEVOPS - LECTURA
# ============================================================
def obtener_wi(wid, expand_relations=True):
    expand = "&$expand=relations" if expand_relations else ""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{wid}?api-version=7.1{expand}"
    r = requests.get(url, headers=h(), timeout=15)
    return r.json() if r.status_code == 200 else None


def obtener_varios(ids):
    if not ids:
        return []
    todos = []
    for i in range(0, len(ids), 200):
        lote = ids[i:i+200]
        ids_str = ",".join(str(x) for x in lote)
        url = (f"{BASE}/{PROJ}/_apis/wit/workitems?ids={ids_str}"
               f"&$expand=relations&api-version=7.1")
        r = requests.get(url, headers=h(), timeout=30)
        if r.status_code == 200:
            todos.extend(r.json().get("value", []))
    return todos


def obtener_hijos_recursivo(parent_id):
    """Obtiene TODOS los descendientes recursivos (TCs, subtareas, etc.)."""
    query = f"""
        SELECT [System.Id]
        FROM workitemLinks
        WHERE [Source].[System.Id] = {parent_id}
        AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
        MODE (Recursive)
    """
    url = f"{BASE}/{PROJ}/_apis/wit/wiql?api-version=7.1"
    r = requests.post(url, headers=h(), json={"query": query}, timeout=15)
    if r.status_code != 200:
        return []
    rels = r.json().get("workItemRelations", [])
    ids = []
    for rel in rels:
        if rel.get("target") and rel.get("rel"):
            tid = rel["target"]["id"]
            if tid != parent_id:
                ids.append(tid)
    return ids


# ============================================================
# ANALISIS DE CONTENIDO
# ============================================================
def limpiar_html(html):
    if not html:
        return ""
    t = html
    t = re.sub(r'<br\s*/?>', '\n', t, flags=re.I)
    t = re.sub(r'</p>', '\n', t, flags=re.I)
    t = re.sub(r'</div>', '\n', t, flags=re.I)
    t = re.sub(r'<[^>]+>', '', t)
    t = t.replace('&nbsp;', ' ').replace('&amp;', '&')
    t = t.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    return t.strip()


def analizar_tc(tc):
    """Analiza un TC y devuelve diagnostico."""
    fields = tc.get("fields", {})
    desc = limpiar_html(fields.get("System.Description", ""))
    pasos = limpiar_html(fields.get("Microsoft.VSTS.TCM.Steps", ""))
    contenido = (desc + "\n" + pasos).lower()

    diag = {
        "id": tc.get("id"),
        "title": fields.get("System.Title", ""),
        "state": fields.get("System.State", ""),
        "assigned_to": "",
        "created_by": "",
        "created_date": fields.get("System.CreatedDate", "")[:10],
        "tiene_descripcion": bool(desc.strip()),
        "tiene_gherkin": False,
        "tiene_endpoint": False,
        "tiene_metodo_http": False,
        "tiene_status_code": False,
        "tiene_payload_json": False,
        "endpoints_detectados": [],
        "metodos_detectados": [],
        "longitud_desc": len(desc),
    }

    # Asignado / creador
    asig = fields.get("System.AssignedTo", {})
    if isinstance(asig, dict):
        diag["assigned_to"] = asig.get("displayName", "Sin asignar")
    creator = fields.get("System.CreatedBy", {})
    if isinstance(creator, dict):
        diag["created_by"] = creator.get("displayName", "")

    # Gherkin?
    if re.search(r'\b(feature|scenario|given|when|then|and)\b', contenido):
        diag["tiene_gherkin"] = True

    # Endpoints (paths que comienzan con /)
    paths = re.findall(r'(?:/[a-z0-9_-]+){2,}', contenido)
    if paths:
        diag["tiene_endpoint"] = True
        diag["endpoints_detectados"] = list(set(paths[:5]))

    # URLs https
    urls = re.findall(r'https?://[a-z0-9.\-/]+', contenido)
    if urls:
        diag["tiene_endpoint"] = True
        for u in urls[:3]:
            if u not in diag["endpoints_detectados"]:
                diag["endpoints_detectados"].append(u)

    # Metodos HTTP
    for metodo in ["get", "post", "put", "delete", "patch"]:
        if re.search(rf'\b{metodo}\b', contenido):
            diag["tiene_metodo_http"] = True
            diag["metodos_detectados"].append(metodo.upper())
    diag["metodos_detectados"] = list(set(diag["metodos_detectados"]))

    # Status codes
    if re.search(r'\b(200|201|400|401|403|404|500|503)\b', contenido):
        diag["tiene_status_code"] = True

    # Payload JSON (cualquier {"campo":...} aunque sea descriptivo)
    if re.search(r'[{}]', contenido) and re.search(r'[":]', contenido):
        diag["tiene_payload_json"] = True

    return diag


# ============================================================
# REPORTE
# ============================================================
def generar_reporte(auditorias_por_padre):
    """Genera reporte ejecutivo en Markdown."""
    lineas = []
    lineas.append("# Auditoria de Test Cases - Reporte Ejecutivo")
    lineas.append("")
    lineas.append(f"_Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}_")
    lineas.append(f"_Auditor: {CONFIG.get('user_name', 'QA Lead')}_")
    lineas.append("")
    lineas.append("---")
    lineas.append("")

    # Resumen ejecutivo (totales)
    total_padres = len(auditorias_por_padre)
    total_tcs = sum(len(a["tcs"]) for a in auditorias_por_padre.values())
    total_con_gherkin = sum(
        sum(1 for d in a["tcs"] if d["tiene_gherkin"])
        for a in auditorias_por_padre.values()
    )
    total_con_endpoint = sum(
        sum(1 for d in a["tcs"] if d["tiene_endpoint"])
        for a in auditorias_por_padre.values()
    )
    total_con_metodo = sum(
        sum(1 for d in a["tcs"] if d["tiene_metodo_http"])
        for a in auditorias_por_padre.values()
    )

    lineas.append("## Resumen Ejecutivo")
    lineas.append("")
    lineas.append(f"| Métrica | Valor |")
    lineas.append(f"|---|---|")
    lineas.append(f"| HUs/HTs auditadas | **{total_padres}** |")
    lineas.append(f"| Test Cases analizados | **{total_tcs}** |")
    lineas.append(f"| TCs con estructura Gherkin | **{total_con_gherkin}/{total_tcs}** ({pct(total_con_gherkin, total_tcs)}%) |")
    lineas.append(f"| TCs que mencionan endpoint | **{total_con_endpoint}/{total_tcs}** ({pct(total_con_endpoint, total_tcs)}%) |")
    lineas.append(f"| TCs que mencionan método HTTP | **{total_con_metodo}/{total_tcs}** ({pct(total_con_metodo, total_tcs)}%) |")
    lineas.append("")
    lineas.append("---")
    lineas.append("")

    # Detalle por padre
    lineas.append("## Detalle por HU/HT")
    lineas.append("")

    for padre_id, data in auditorias_por_padre.items():
        padre_info = data["padre"]
        tcs = data["tcs"]

        if not padre_info:
            lineas.append(f"### {padre_id} - NO ENCONTRADO")
            lineas.append("")
            continue

        f = padre_info.get("fields", {})
        tipo = f.get("System.WorkItemType", "")
        titulo = f.get("System.Title", "")
        estado = f.get("System.State", "")

        lineas.append(f"### {tipo} #{padre_id}: {titulo}")
        lineas.append("")
        lineas.append(f"**Estado:** {estado}  |  **TCs encontrados:** {len(tcs)}")
        lineas.append("")

        if not tcs:
            lineas.append("⚠️ **Sin TCs hijos.** Necesita generación de TCs antes de automatizar.")
            lineas.append("")
            continue

        # Tabla resumen
        lineas.append("| ID | Title | Creado por | Estado | Gherkin | Endpoint | Método |")
        lineas.append("|---|---|---|---|---|---|---|")
        for d in tcs:
            tit = d["title"][:50].replace("|", "\\|")
            gh = "✅" if d["tiene_gherkin"] else "❌"
            ep = "✅" if d["tiene_endpoint"] else "❌"
            mh = ",".join(d["metodos_detectados"]) if d["metodos_detectados"] else "❌"
            lineas.append(f"| #{d['id']} | {tit} | {d['created_by'][:25]} | {d['state']} | {gh} | {ep} | {mh} |")
        lineas.append("")

        # Endpoints detectados en este padre
        all_endpoints = set()
        for d in tcs:
            all_endpoints.update(d["endpoints_detectados"])
        if all_endpoints:
            lineas.append("**Endpoints detectados en los TCs:**")
            for e in sorted(all_endpoints):
                lineas.append(f"- `{e}`")
            lineas.append("")

        # Creadores únicos
        creadores = Counter(d["created_by"] for d in tcs if d["created_by"])
        if creadores:
            lineas.append("**Creadores:**")
            for nombre, cant in creadores.most_common():
                lineas.append(f"- {nombre} ({cant} TCs)")
            lineas.append("")

        # Diagnóstico por padre
        tcs_gherkin = sum(1 for d in tcs if d["tiene_gherkin"])
        tcs_endpoint = sum(1 for d in tcs if d["tiene_endpoint"])

        lineas.append("**Diagnóstico:**")
        if tcs_gherkin == len(tcs):
            lineas.append("- ✅ Todos los TCs usan estructura Gherkin")
        elif tcs_gherkin > 0:
            lineas.append(f"- ⚠️ Solo {tcs_gherkin}/{len(tcs)} TCs usan Gherkin (inconsistencia)")
        else:
            lineas.append("- ❌ Ningún TC usa Gherkin estructurado")

        if tcs_endpoint == len(tcs):
            lineas.append("- ✅ Todos los TCs mencionan endpoint")
        elif tcs_endpoint > 0:
            lineas.append(f"- ⚠️ Solo {tcs_endpoint}/{len(tcs)} TCs mencionan endpoint")
        else:
            lineas.append("- ❌ Ningún TC menciona endpoint (no son automatizables sin info externa)")

        lineas.append("")
        lineas.append("---")
        lineas.append("")

    # Recomendaciones
    lineas.append("## Recomendaciones del QA Lead")
    lineas.append("")

    if total_con_endpoint == 0:
        lineas.append("### ❌ Crítico: Los TCs NO son auto-ejecutables")
        lineas.append("")
        lineas.append("Ninguno de los TCs auditados menciona endpoints/URLs en su contenido.")
        lineas.append("**Opciones:**")
        lineas.append("1. Mantener un catálogo externo (JSON) que mapee `HT_id -> endpoint`")
        lineas.append("2. Regenerar los TCs con qa-cli pidiendo endpoints embebidos")
        lineas.append("3. Conversar con el equipo creador para mejorar el estándar")
        lineas.append("")
    elif total_con_endpoint < total_tcs:
        lineas.append("### ⚠️ Cobertura parcial")
        lineas.append("")
        lineas.append(f"Solo {total_con_endpoint}/{total_tcs} TCs mencionan endpoint.")
        lineas.append("Necesitarás un híbrido: parsing donde se pueda + catálogo manual.")
        lineas.append("")
    else:
        lineas.append("### ✅ Excelente: TCs listos para automatizar")
        lineas.append("")

    if total_con_gherkin < total_tcs:
        lineas.append("### ⚠️ Inconsistencia de formato")
        lineas.append("")
        lineas.append("No todos los TCs usan Gherkin. Esto dificulta:")
        lineas.append("- Automatización con frameworks BDD (Karate, Serenity)")
        lineas.append("- Trazabilidad criterio→TC")
        lineas.append("- Mantenibilidad a largo plazo")
        lineas.append("")

    lineas.append("### Próximos pasos sugeridos")
    lineas.append("")
    lineas.append("1. **Validar este reporte** con el líder del equipo que creó los TCs")
    lineas.append("2. **Conversar con dev lead** sobre permisos para ejecutar contra LAB/DEV")
    lineas.append("3. **Piloto con 1 sola HT** antes de escalar a las 6")
    lineas.append("4. **Definir si los TCs se regeneran** o se mantienen con catálogo externo")
    lineas.append("")

    return "\n".join(lineas)


def pct(parte, total):
    if total == 0:
        return 0
    return round((parte / total) * 100, 1)


# ============================================================
# MAIN
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("\nUso: py auditar_tcs.py <ID1> [<ID2> ...]")
        print("Ejemplo: py auditar_tcs.py 1083516 1083517 1083518")
        sys.exit(1)

    ids_padres = [int(x) for x in sys.argv[1:] if x.isdigit()]
    if not ids_padres:
        print("[ERROR] IDs invalidos")
        sys.exit(1)

    print()
    print("#" * 70)
    print(f"#  AUDITORIA DE TEST CASES")
    print(f"#  Padres a auditar: {len(ids_padres)}")
    print("#" * 70)

    auditorias = {}

    for padre_id in ids_padres:
        print(f"\n[INFO] Auditando padre #{padre_id}...")

        # Obtener el padre
        padre = obtener_wi(padre_id, expand_relations=False)
        if not padre:
            print(f"  [ERROR] No se encontro #{padre_id}")
            auditorias[padre_id] = {"padre": None, "tcs": []}
            continue

        tit_padre = padre.get("fields", {}).get("System.Title", "")[:60]
        tipo_padre = padre.get("fields", {}).get("System.WorkItemType", "")
        print(f"  {tipo_padre}: {tit_padre}")

        # Obtener todos los descendientes
        ids_descendientes = obtener_hijos_recursivo(padre_id)
        if not ids_descendientes:
            print(f"  [INFO] Sin descendientes")
            auditorias[padre_id] = {"padre": padre, "tcs": []}
            continue

        # Obtener detalle de descendientes
        descendientes = obtener_varios(ids_descendientes)

        # Filtrar solo Casos de Prueba
        tcs = [d for d in descendientes
               if d.get("fields", {}).get("System.WorkItemType") == "Caso de prueba"]

        print(f"  [OK] {len(tcs)} Test Cases encontrados (de {len(descendientes)} descendientes totales)")

        # Analizar cada TC
        diagnosticos = [analizar_tc(tc) for tc in tcs]
        auditorias[padre_id] = {"padre": padre, "tcs": diagnosticos}

    # Generar reporte
    reporte = generar_reporte(auditorias)

    # Guardar
    output_dir = Path("output") / "auditoria"
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta = output_dir / f"auditoria_{ts}.md"

    with open(ruta, "w", encoding="utf-8") as f:
        f.write(reporte)

    # Tambien guardar el JSON crudo
    ruta_json = output_dir / f"auditoria_{ts}.json"
    with open(ruta_json, "w", encoding="utf-8") as f:
        data_export = {
            pid: {
                "padre_title": data["padre"]["fields"]["System.Title"] if data["padre"] else None,
                "tcs": data["tcs"],
            }
            for pid, data in auditorias.items()
        }
        json.dump(data_export, f, indent=2, ensure_ascii=False, default=str)

    print()
    print("=" * 70)
    print("REPORTE GENERADO")
    print("=" * 70)
    print(f"  Markdown: {ruta.absolute()}")
    print(f"  JSON:     {ruta_json.absolute()}")
    print()
    print("  Abrir reporte:")
    print(f"     code \"{ruta}\"")
    print()


if __name__ == "__main__":
    main()