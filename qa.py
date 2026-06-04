"""
QA Toolkit - Un solo script para todo lo que necesitas.

Te pregunta que quieres y te trae el detalle listo para Copilot.

Uso: py qa.py
"""

import requests
import base64
import os
import sys
import re
import subprocess
from datetime import datetime
from getpass import getpass

ORGANIZATION = "SuraColombia"
PROJECT = "Gerencia_Tecnologia"
BASE_URL = f"https://dev.azure.com/{ORGANIZATION}"

PAT = os.environ.get("AZURE_DEVOPS_PAT")
if not PAT:
    print("\n[INFO] Pega tu PAT (no se mostrara):")
    PAT = getpass("PAT: ").strip()
if not PAT:
    sys.exit(1)


def get_headers():
    token = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Content-Type": "application/json"}


HEADERS = get_headers()


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


def obtener_item(wi_id):
    """Obtiene el detalle completo de un work item."""
    url = (f"{BASE_URL}/{PROJECT}/_apis/wit/workitems/{wi_id}"
           f"?$expand=relations&api-version=7.1")
    r = requests.get(url, headers=HEADERS, timeout=15)
    if r.status_code == 200:
        return r.json()
    elif r.status_code == 404:
        print(f"[ERROR] WI #{wi_id} no existe o sin acceso.")
        return None
    else:
        print(f"[ERROR] {r.status_code}: {r.text[:200]}")
        return None


def obtener_hijos_ids(parent_id):
    """Lista todos los hijos recursivos de un padre."""
    query = f"""
        SELECT [System.Id]
        FROM workitemLinks
        WHERE [Source].[System.Id] = {parent_id}
        AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
        MODE (Recursive)
    """
    url = f"{BASE_URL}/{PROJECT}/_apis/wit/wiql?api-version=7.1"
    r = requests.post(url, headers=HEADERS, json={"query": query}, timeout=15)
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


def obtener_varios(ids):
    """Obtiene detalles de varios items en lote."""
    if not ids:
        return []
    todos = []
    for i in range(0, len(ids), 200):
        lote = ids[i:i + 200]
        ids_str = ",".join(str(x) for x in lote)
        url = (f"{BASE_URL}/{PROJECT}/_apis/wit/workitems?ids={ids_str}"
               f"&$expand=relations&api-version=7.1")
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 200:
            todos.extend(r.json().get("value", []))
    return todos


def item_a_markdown(item, nivel_h=2):
    """Convierte un work item a Markdown formateado."""
    f = item.get("fields", {})
    wid = item.get("id")
    tipo = f.get("System.WorkItemType", "N/A")
    titulo = f.get("System.Title", "Sin titulo")
    estado = f.get("System.State", "N/A")
    asignado = f.get("System.AssignedTo", {})
    asignado_nombre = (asignado.get("displayName", "Sin asignar")
                       if isinstance(asignado, dict) else "Sin asignar")
    prioridad = f.get("Microsoft.VSTS.Common.Priority", "N/A")
    iteracion = f.get("System.IterationPath", "N/A")
    tags = f.get("System.Tags", "")
    desc = limpiar_html(f.get("System.Description", ""))
    crit = limpiar_html(f.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))
    repro = limpiar_html(f.get("Microsoft.VSTS.TCM.ReproSteps", ""))

    h = "#" * nivel_h
    lineas = []
    lineas.append(f"{h} {tipo} #{wid}: {titulo}")
    lineas.append("")
    lineas.append("| Campo | Valor |")
    lineas.append("|---|---|")
    lineas.append(f"| **Estado** | {estado} |")
    lineas.append(f"| **Asignado** | {asignado_nombre} |")
    lineas.append(f"| **Prioridad** | {prioridad} |")
    lineas.append(f"| **Iteracion** | {iteracion} |")
    if tags:
        lineas.append(f"| **Tags** | {tags} |")
    lineas.append(f"| **URL** | https://dev.azure.com/{ORGANIZATION}/{PROJECT}/_workitems/edit/{wid} |")
    lineas.append("")
    lineas.append(f"{h}# Descripcion")
    lineas.append("")
    lineas.append(desc if desc else "_(sin descripcion)_")
    lineas.append("")
    if crit:
        lineas.append(f"{h}# Criterios de Aceptacion")
        lineas.append("")
        lineas.append(crit)
        lineas.append("")
    if repro:
        lineas.append(f"{h}# Pasos de Reproduccion")
        lineas.append("")
        lineas.append(repro)
        lineas.append("")
    return "\n".join(lineas)


def generar_md_individual(item):
    """Genera MD para un solo item."""
    f = item.get("fields", {})
    wid = item.get("id")
    tipo = f.get("System.WorkItemType", "Item")
    titulo = f.get("System.Title", "")[:50]

    md = [f"# {tipo} #{wid} - {titulo}", ""]
    md.append(f"_Extraido el {datetime.now().strftime('%d/%m/%Y %H:%M')}_")
    md.append("")
    md.append("---")
    md.append("")
    md.append(item_a_markdown(item, nivel_h=2))
    md.append("---")
    md.append("")
    md.append("## Prompt sugerido para Copilot Chat")
    md.append("")
    md.append("```")
    md.append("Lee .github/copilot-instructions.md y genera los Test Cases para este work item.")
    md.append("")
    md.append("REGLA CRITICA de Sura:")
    md.append("- Historia de Usuario (HU): MAXIMO 4 TCs (ideal 3-4)")
    md.append("- Historia Tecnica (HT): MAXIMO 3 TCs (ideal 2-3)")
    md.append("")
    md.append("Formato OBLIGATORIO por cada TC:")
    md.append("- Title en ESPANOL descriptivo (no IDs)")
    md.append("- Description con Feature + Scenario + Steps en Gherkin")
    md.append("  (keywords Given/When/Then/And en INGLES, contenido en ESPANOL)")
    md.append("- Campos custom: Tipo ejecucion=Manual, Fase=Construccion, Nivel prueba=E2E")
    md.append("- Prioridad: Alta/Media/Baja segun corresponda")
    md.append("")
    md.append("Cobertura priorizada:")
    md.append("- TC #1: Happy path principal (Alta)")
    md.append("- TC #2: Escenario fallido critico (Alta)")
    md.append("- TC #3: Edge case o validacion clave (Media)")
    md.append("- TC #4 (opcional): Seguridad / trazabilidad (Media/Baja)")
    md.append("```")
    return "\n".join(md)


def generar_md_padre_e_hijos(padre, hijos):
    """Genera MD para un padre y todos sus hijos agrupados por tipo."""
    f = padre.get("fields", {})
    wid = padre.get("id")
    tipo = f.get("System.WorkItemType", "Item")
    titulo = f.get("System.Title", "")

    # Agrupar hijos por tipo
    agrupados = {}
    for it in hijos:
        t = it.get("fields", {}).get("System.WorkItemType", "Otro")
        agrupados.setdefault(t, []).append(it)

    orden = ["Historia", "User Story", "Product Backlog Item",
             "Historia tecnica", "Historia técnica",
             "Tarea", "Task", "Bug", "Feature", "Test Case"]
    tipos_ordenados = sorted(agrupados.keys(),
                              key=lambda t: orden.index(t) if t in orden else 999)

    md = [f"# {tipo} #{wid} - {titulo}", ""]
    md.append(f"_Extraido el {datetime.now().strftime('%d/%m/%Y %H:%M')}_")
    md.append("")
    md.append(f"**Total de items hijos:** {len(hijos)}")
    md.append("")
    md.append("## Indice")
    md.append("")
    for tipo_n in tipos_ordenados:
        md.append(f"### {tipo_n} ({len(agrupados[tipo_n])})")
        for it in agrupados[tipo_n]:
            ff = it.get("fields", {})
            md.append(f"- #{it['id']} - {ff.get('System.Title', '')} `{ff.get('System.State', '')}`")
        md.append("")
    md.append("---")
    md.append("")
    md.append("# Detalle del padre")
    md.append("")
    md.append(item_a_markdown(padre, nivel_h=2))
    md.append("---")
    md.append("")

    # Detalle de cada hijo agrupado
    for tipo_n in tipos_ordenados:
        md.append(f"# {tipo_n.upper()}")
        md.append("")
        for it in agrupados[tipo_n]:
            md.append(item_a_markdown(it, nivel_h=2))
            md.append("---")
            md.append("")

    # Prompt final
    md.append("## Prompt sugerido para Copilot Chat")
    md.append("")
    md.append("```")
    md.append("Lee .github/copilot-instructions.md y genera los Test Cases para CADA item.")
    md.append("")
    md.append("REGLA CRITICA de Sura:")
    md.append("- Por cada Historia de Usuario (HU): MAXIMO 4 TCs (ideal 3-4)")
    md.append("- Por cada Historia Tecnica (HT): MAXIMO 3 TCs (ideal 2-3)")
    md.append("- NO te excedas. Calidad sobre cantidad.")
    md.append("")
    md.append("Formato OBLIGATORIO por cada TC:")
    md.append("- Title en ESPANOL descriptivo (no IDs)")
    md.append("- Description con Feature + Scenario + Steps en Gherkin")
    md.append("  (keywords Given/When/Then/And en INGLES, contenido en ESPANOL)")
    md.append("- Campos custom: Tipo ejecucion=Manual, Fase=Construccion, Nivel prueba=E2E")
    md.append("- Prioridad: Alta/Media/Baja segun corresponda")
    md.append("")
    md.append("Procesa primero las Historias, luego las Historias Tecnicas.")
    md.append("Las Tareas NO requieren test cases (son trabajo tecnico interno).")
    md.append("```")
    return "\n".join(md)


def abrir_en_vscode(archivo):
    """Intenta abrir el archivo en VS Code."""
    try:
        subprocess.Popen(["code", archivo], shell=True)
        print(f"[OK] Archivo abierto en VS Code: {archivo}")
    except Exception:
        print(f"[INFO] Para abrir manualmente: code {archivo}")


# ============================================================
# MENU PRINCIPAL
# ============================================================
def main():
    print("\n" + "#" * 60)
    print("# QA TOOLKIT - Azure DevOps")
    print("#" * 60)
    print("""
  Que quieres hacer?

  1. Traer UN solo item (HU, Tarea, HT, Feature, etc.)
  2. Traer UN padre + TODOS sus hijos (Feature con sus HUs, Epica completa)
  0. Salir
""")
    op = input("  Opcion: ").strip()

    if op == "0":
        return

    if op not in ("1", "2"):
        print("  [ERROR] Opcion invalida.")
        return

    wid_str = input("  Ingresa el ID del work item: ").strip()
    if not wid_str.isdigit():
        print("  [ERROR] El ID debe ser numerico.")
        return
    wid = int(wid_str)

    print(f"\n[INFO] Buscando WI #{wid}...")
    item = obtener_item(wid)
    if not item:
        return

    titulo_item = item.get("fields", {}).get("System.Title", "")
    tipo_item = item.get("fields", {}).get("System.WorkItemType", "")
    print(f"[OK] Encontrado: {tipo_item} #{wid} - {titulo_item}")

    if op == "1":
        # Solo este item
        md = generar_md_individual(item)
        archivo = f"WI_{wid}.md"
    else:
        # Padre + hijos
        print(f"[INFO] Buscando hijos del WI #{wid}...")
        ids_hijos = obtener_hijos_ids(wid)
        if not ids_hijos:
            print("[INFO] No tiene hijos. Generando solo el item padre.")
            md = generar_md_individual(item)
        else:
            print(f"[OK] {len(ids_hijos)} hijos encontrados. Descargando...")
            hijos = obtener_varios(ids_hijos)
            md = generar_md_padre_e_hijos(item, hijos)
        archivo = f"WI_{wid}_completo.md"

    # Guardar
    with open(archivo, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"\n[SUCCESS] Archivo generado: {archivo}")
    print(f"          Ruta: {os.path.abspath(archivo)}")
    print()
    print(">>> Siguiente paso:")
    print(f"    1. Abrir el archivo: code {archivo}")
    print("    2. Copiar todo el contenido (Ctrl+A, Ctrl+C)")
    print("    3. Pegar en Copilot Chat con: 'Genera los test cases segun .github/copilot-instructions.md'")
    print()

    abrir = input("  Abrir el archivo en VS Code ahora? (s/n): ").strip().lower()
    if abrir == "s":
        abrir_en_vscode(archivo)


if __name__ == "__main__":
    main()
