# -*- coding: utf-8 -*-
"""
ejecutar_karate.py v2 - Puente Python <-> Karate integrado con qa-cli.
 
v2: Sintaxis Karate corregida:
    - apikey se define con '* def apikeyValor = ...'
    - Headers usan '#(apikeyValor)' (sintaxis valida)
    - Subprocess con shell=True para mvn en Windows
 
Uso:
    py ejecutar_karate.py <ID_HT> [--ambiente lab|dev] [--dry-run]
"""
 
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
 
import requests
 
CONFIG_PATH = "config.json"
CATALOGO_PATH = "tcs_catalog.json"
KARATE_PROJECT = Path("C:/Sura/karate-glosas")
KARATE_DINAMICOS = KARATE_PROJECT / "src/test/java/sura/glosas/dinamicos"
KARATE_TARGET = KARATE_PROJECT / "target"
OUTPUT_DIR = Path("output/ejecuciones_karate")
 
ESTADO_EN_PROGRESO = "En progreso"
ESTADO_PASS = "Cerrado"
ESTADO_FAIL = "Impedimento"
 
 
def cargar_config():
    if not os.path.exists(CONFIG_PATH):
        print(f"[ERROR] No se encontro {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)
 
 
def cargar_catalogo():
    if not os.path.exists(CATALOGO_PATH):
        print(f"[ERROR] No se encontro {CATALOGO_PATH}")
        sys.exit(1)
    with open(CATALOGO_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)
 
 
CONFIG = cargar_config()
CATALOGO = cargar_catalogo()
ORG = CONFIG["organization"]
PROJ = CONFIG["project"]
BASE = f"https://dev.azure.com/{ORG}"
 
PAT = os.environ.get("AZURE_DEVOPS_PAT")
if not PAT:
    from getpass import getpass
    PAT = getpass("PAT de Azure DevOps: ").strip()
if not PAT:
    print("[ERROR] PAT requerido")
    sys.exit(1)
 
 
def h_json():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json"}
 
 
def h_patch():
    t = base64.b64encode(f":{PAT}".encode()).decode()
    return {"Authorization": f"Basic {t}", "Content-Type": "application/json-patch+json"}
 
 
def obtener_wi(wid):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{wid}?api-version=7.1"
    r = requests.get(url, headers=h_json(), timeout=15)
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
        r = requests.get(url, headers=h_json(), timeout=30)
        if r.status_code == 200:
            todos.extend(r.json().get("value", []))
    return todos
 
 
def obtener_descendientes(parent_id):
    query = f"""
        SELECT [System.Id]
        FROM workitemLinks
        WHERE [Source].[System.Id] = {parent_id}
        AND [System.Links.LinkType] = 'System.LinkTypes.Hierarchy-Forward'
        MODE (Recursive)
    """
    url = f"{BASE}/{PROJ}/_apis/wit/wiql?api-version=7.1"
    r = requests.post(url, headers=h_json(), json={"query": query}, timeout=15)
    if r.status_code != 200:
        return []
    rels = r.json().get("workItemRelations", [])
    return [rel["target"]["id"] for rel in rels
            if rel.get("target") and rel["target"]["id"] != parent_id]
 
 
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
 
 
def generar_feature_dinamico(tc, tc_config, ambiente_config, ht_id):
    """Genera un .feature de Karate dinamicamente para este TC especifico."""
    tc_id = tc["id"]
    titulo = tc.get("fields", {}).get("System.Title", "")
    gherkin = limpiar_html(tc.get("fields", {}).get("System.Description", ""))
 
    host = ambiente_config["host"]
    path = tc_config["path_template"]
    for var, key in tc_config.get("path_params", {}).items():
        valor = CATALOGO.get("datos_prueba", {}).get(key, key)
        path = path.replace("{" + var + "}", str(valor))
 
    url_completa = f"https://{host}{path}"
    query_params = tc_config.get("query_params", {})
    if query_params:
        qs = "&".join(f"{k}={v}" for k, v in query_params.items())
        url_completa = f"{url_completa}?{qs}"
 
    headers_extra = tc_config.get("headers_extra", {})
    business_line = headers_extra.get("Business-Line", "")
 
    body = tc_config.get("body")
    body_json_str = json.dumps(body, indent=2) if body else None
 
    validaciones = tc_config.get("validaciones", {})
    status_esperado = validaciones.get("status_esperado", [200])
    tiempo_max = validaciones.get("tiempo_max_ms", 5000)
    body_contiene = validaciones.get("body_contiene", [])
    body_contiene_alguno = validaciones.get("body_contiene_alguno", [])
 
    gherkin_lines = [f"  # {line}" for line in gherkin.split("\n") if line.strip()]
    gherkin_comentarios = "\n".join(gherkin_lines)
 
    metodo = tc_config["method"]
    escenario = tc_config.get("escenario", "default")
    apikey_tipo = tc_config.get("apikey_tipo", "valida")
 
    titulo_safe = titulo.replace("'", "").replace('"', '')
 
    lineas = []
    lineas.append(f"Feature: TC #{tc_id} - HT #{ht_id} - {titulo_safe[:80]}")
    lineas.append("")
    lineas.append("  Background:")
    lineas.append(f"    * url '{url_completa}'")
 
    # SINTAXIS CORREGIDA: definimos apikey como variable previa
    if apikey_tipo == "valida":
        lineas.append("    * def apikeyValor = karate.properties['apikeyValida']")
    elif apikey_tipo == "invalida":
        lineas.append("    * def apikeyValor = 'INVALID_KEY_FOR_TESTING_ONLY'")
    else:
        lineas.append("    * def apikeyValor = ''")
 
    lineas.append("")
    lineas.append(f"  @tc{tc_id} @ht{ht_id} @{escenario}")
    lineas.append(f"  Scenario: {titulo_safe}")
    lineas.append("")
    lineas.append("    # ============================================================")
    lineas.append("    # GHERKIN ORIGINAL DEL TC EN AZURE DEVOPS:")
    lineas.append("    # ============================================================")
    lineas.append(gherkin_comentarios)
    lineas.append("    # ============================================================")
    lineas.append("")
    lineas.append("    # Configuracion del request")
 
    # SINTAXIS CORREGIDA: '#(apikeyValor)' con comillas
    headers_line = (
        "    * configure headers = "
        "{ 'Content-Type': 'application/json', "
        "'x-apikey': '#(apikeyValor)', "
        f"'Business-Line': '{business_line}' " + "}"
    )
    lineas.append(headers_line)
    lineas.append("")
 
    if body_json_str and metodo.upper() in ("POST", "PUT", "PATCH"):
        lineas.append("    # Request body desde catalogo")
        lineas.append("    * request")
        lineas.append('    """')
        for body_line in body_json_str.split("\n"):
            lineas.append("    " + body_line)
        lineas.append('    """')
        lineas.append("")
 
    lineas.append("    # Ejecucion")
    lineas.append(f"    * method {metodo}")
    lineas.append("")
    lineas.append("    # Validaciones")
    lineas.append("    * print 'Status:', responseStatus")
    lineas.append("    * print 'Tiempo:', responseTime + 'ms'")
 
    status_list = "[" + ", ".join(str(s) for s in status_esperado) + "]"
    lineas.append(f"    * def statusValidos = {status_list}")
    lineas.append("    * assert statusValidos.indexOf(responseStatus) >= 0")
    lineas.append(f"    * assert responseTime < {tiempo_max}")
 
    for texto in body_contiene:
        texto_safe = texto.replace("'", "")
        lineas.append(f"    * match response + '' contains '{texto_safe}'")
 
    if body_contiene_alguno:
        opciones_safe = [t.replace("'", "") for t in body_contiene_alguno]
        lineas.append("    * def opciones = " + json.dumps(opciones_safe))
        lineas.append("    * def responseStr = (response + '').toLowerCase()")
        lineas.append("    * def encontrado = opciones.find(opt => responseStr.indexOf(opt.toLowerCase()) >= 0)")
        lineas.append("    * assert encontrado != null")
 
    lineas.append(f"    * print '[TC #{tc_id}] PASS - status:', responseStatus")
    lineas.append("")
 
    return "\n".join(lineas)
 
 
def ejecutar_karate(feature_path, apikey_valor):
    """Ejecuta Karate via Maven."""
    feature_relativo = str(feature_path.relative_to(KARATE_PROJECT)).replace("\\", "/")
    feature_para_karate = feature_relativo.replace("src/test/java/", "")
 
    cmd_str = (
        f'mvn test -Dkarate.options=classpath:{feature_para_karate} '
        f'-DapikeyValida={apikey_valor} -q'
    )
 
    print(f"        [KARATE] {feature_para_karate}")
    inicio = time.time()
 
    try:
        result = subprocess.run(
            cmd_str,
            cwd=str(KARATE_PROJECT),
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
            shell=True
        )
        duracion = int((time.time() - inicio) * 1000)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duracion_ms": duracion,
            "paso": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1, "stdout": "", "stderr": "Timeout (120s)",
            "duracion_ms": 120000, "paso": False,
        }
    except Exception as e:
        return {
            "exit_code": -1, "stdout": "", "stderr": str(e),
            "duracion_ms": 0, "paso": False,
        }
 
 
def cambiar_estado_tc(tc_id, nuevo_estado):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{"op": "add", "path": "/fields/System.State", "value": nuevo_estado}]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)
 
 
def agregar_comentario(tc_id, texto):
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments?api-version=7.1-preview.4"
    r = requests.post(url, headers=h_json(), json={"text": texto}, timeout=15)
    return r.status_code in (200, 201)
 
 
def subir_attachment(archivo_path):
    nombre = Path(archivo_path).name
    url = f"{BASE}/{PROJ}/_apis/wit/attachments?fileName={nombre}&api-version=7.1"
    with open(archivo_path, "rb") as f:
        contenido = f.read()
    t = base64.b64encode(f":{PAT}".encode()).decode()
    headers = {"Authorization": f"Basic {t}", "Content-Type": "application/octet-stream"}
    r = requests.post(url, headers=headers, data=contenido, timeout=30)
    if r.status_code in (200, 201):
        return r.json().get("url")
    return None
 
 
def vincular_attachment(tc_id, attachment_url, nombre):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{
        "op": "add",
        "path": "/relations/-",
        "value": {
            "rel": "AttachedFile",
            "url": attachment_url,
            "attributes": {"comment": f"Evidencia Karate - {nombre}"},
        }
    }]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)
 
 
def construir_comentario(tc_id, ht_id, titulo, escenario, ambiente, ejecutor,
                         resultado_karate, feature_generado_path):
    paso = resultado_karate["paso"]
    badge = "PASS" if paso else "FAIL"
    icono = "&#9989;" if paso else "&#10060;"
    color = "#28a745" if paso else "#dc3545"
    exit_code = resultado_karate["exit_code"]
    duracion = resultado_karate["duracion_ms"]
 
    stdout_preview = resultado_karate["stdout"][-1500:] if resultado_karate["stdout"] else "(sin output)"
    stdout_preview = stdout_preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
 
    stderr_section = ""
    if resultado_karate["stderr"]:
        stderr = resultado_karate["stderr"][-800:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        stderr_section = (
            "<h4 style='margin:8px 0 6px 0;color:#c00;'>Errores</h4>"
            f"<pre style='background:#fff3f3;color:#c00;padding:10px;font-size:12px;max-height:200px;overflow-y:auto;'>{stderr}</pre>"
        )
 
    return f"""
<div style='font-family:Segoe UI,Arial,sans-serif;border-left:4px solid {color};padding:12px 18px;background:#f8f9fa;'>
    <h3 style='margin:0 0 12px 0;color:{color};'>{icono} {badge} - Ejecucion Karate (qa-cli)</h3>
    <table style='border-collapse:collapse;margin-bottom:12px;'>
        <tr><td style='padding:3px 12px 3px 0;'><b>Engine:</b></td><td>Karate 1.4.1 (Java)</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ejecutor:</b></td><td>{ejecutor}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Fecha:</b></td><td>{datetime.now().strftime("%d/%m/%Y %H:%M:%S")}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ambiente:</b></td><td><b>{ambiente.upper()}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Escenario:</b></td><td><b>{escenario}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Duracion:</b></td><td>{duracion} ms</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Exit code:</b></td><td>{exit_code}</td></tr>
    </table>
    <h4 style='margin:8px 0 6px 0;color:#333;'>Output de Karate</h4>
    <pre style='background:#1e1e1e;color:#dcdcdc;padding:10px;border-radius:4px;font-size:11px;max-height:300px;overflow-y:auto;white-space:pre-wrap;'>{stdout_preview}</pre>
    {stderr_section}
    <p style='margin-top:10px;font-size:13px;color:#666;'>Feature: <code>{feature_generado_path}</code></p>
</div>
""".strip()
 
 
def procesar_tc(tc, tc_config, ambiente_key, ambiente_config, ejecutor,
                ht_id, dry_run, idx, total):
    tc_id = tc["id"]
    titulo = tc.get("fields", {}).get("System.Title", "")
    escenario = tc_config.get("escenario", "default")
 
    print(f"\n[{idx}/{total}] TC #{tc_id}: {titulo[:55]}")
    print(f"        Escenario: {escenario}")
 
    print(f"        [GEN] Generando .feature dinamico...")
    feature_content = generar_feature_dinamico(tc, tc_config, ambiente_config, ht_id)
    KARATE_DINAMICOS.mkdir(parents=True, exist_ok=True)
    feature_path = KARATE_DINAMICOS / f"tc_{tc_id}.feature"
    with open(feature_path, "w", encoding="utf-8") as f:
        f.write(feature_content)
    print(f"        [GEN] Feature: {feature_path.name}")
 
    if dry_run:
        print(f"        [DRY-RUN] Feature generado, no ejecuto Karate")
        return {"tc_id": tc_id, "resultado": "DRY-RUN", "escenario": escenario}
 
    cambiar_estado_tc(tc_id, ESTADO_EN_PROGRESO)
    print(f"        [OK] Estado -> {ESTADO_EN_PROGRESO}")
 
    apikey_valida = os.environ.get(ambiente_config["apikey_env"], "")
    resultado = ejecutar_karate(feature_path, apikey_valida)
    paso = resultado["paso"]
    print(f"        [KARATE] {'PASS' if paso else 'FAIL'} (exit {resultado['exit_code']}, {resultado['duracion_ms']}ms)")
 
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = OUTPUT_DIR / f"HT_{ht_id}" / f"TC_{tc_id}"
    carpeta.mkdir(parents=True, exist_ok=True)
 
    evidencia = {
        "tc_id": tc_id, "ht_id": ht_id, "titulo": titulo,
        "escenario": escenario, "ambiente": ambiente_key,
        "ejecutor": ejecutor, "timestamp": datetime.now().isoformat(),
        "feature_path": str(feature_path),
        "feature_content": feature_content,
        "karate_result": {
            "exit_code": resultado["exit_code"],
            "duracion_ms": resultado["duracion_ms"],
            "stdout": resultado["stdout"][-3000:],
            "stderr": resultado["stderr"][-1500:] if resultado["stderr"] else "",
            "paso": paso,
        },
    }
 
    archivo_evidencia = carpeta / f"evidencia_karate_{ts}.json"
    with open(archivo_evidencia, "w", encoding="utf-8") as f:
        json.dump(evidencia, f, indent=2, ensure_ascii=False)
    print(f"        [EVID] {archivo_evidencia.name}")
 
    attachment_url = subir_attachment(archivo_evidencia)
    if attachment_url:
        vincular_attachment(tc_id, attachment_url, archivo_evidencia.name)
        print(f"        [OK] Attachment vinculado")
 
    comentario = construir_comentario(
        tc_id, ht_id, titulo, escenario, ambiente_key, ejecutor,
        resultado, feature_path.name
    )
    if agregar_comentario(tc_id, comentario):
        print(f"        [OK] Comentario agregado")
 
    estado_final = ESTADO_PASS if paso else ESTADO_FAIL
    cambiar_estado_tc(tc_id, estado_final)
    print(f"        [OK] Estado final -> {estado_final}")
 
    if not paso:
        print(f"\n        Crear bug en ADO?")
        resp = input(f"        Crear bug? (s/n): ").strip().lower()
        if resp == "s":
            subprocess.run("py crear_bug.py --tc " + str(tc_id), shell=True)
 
    return {
        "tc_id": tc_id, "titulo": titulo,
        "resultado": "PASS" if paso else "FAIL",
        "escenario": escenario,
    }
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("padre_id", type=int)
    ap.add_argument("--ambiente", choices=["dev", "lab"], default="lab")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
 
    padre_id = args.padre_id
    ambiente_key = args.ambiente
    dry_run = args.dry_run
 
    print()
    print("#" * 70)
    print(f"#  EJECUTOR KARATE INTEGRADO v2")
    print(f"#  HU/HT: #{padre_id}  |  Ambiente: {ambiente_key.upper()}")
    print(f"#  Modo: {'DRY-RUN' if dry_run else 'REAL'}")
    print("#" * 70)
 
    if not KARATE_PROJECT.exists():
        print(f"[ERROR] No se encontro proyecto Karate")
        sys.exit(1)
    print(f"\n[1] Proyecto Karate: {KARATE_PROJECT}")
 
    padre = obtener_wi(padre_id)
    if not padre:
        print(f"[ERROR] No se encontro #{padre_id}")
        sys.exit(1)
    titulo_padre = padre.get("fields", {}).get("System.Title", "")
    print(f"[2] HU/HT: {titulo_padre[:60]}")
 
    ids = obtener_descendientes(padre_id)
    descendientes = obtener_varios(ids)
    tcs = [d for d in descendientes
           if d.get("fields", {}).get("System.WorkItemType") == "Caso de prueba"]
 
    if not tcs:
        print(f"[ERROR] Sin Test Cases")
        sys.exit(1)
    print(f"[3] {len(tcs)} Test Cases encontrados")
 
    tcs_validos = []
    for tc in tcs:
        titulo_tc = tc.get("fields", {}).get("System.Title", "").strip().lower()
        desc_tc = limpiar_html(tc.get("fields", {}).get("System.Description", ""))
        if titulo_tc == "pruebas de calidad" and len(desc_tc) < 50:
            continue
        tcs_validos.append(tc)
 
    catalogados = []
    no_catalogados = []
    for tc in tcs_validos:
        if str(tc["id"]) in CATALOGO.get("tcs", {}):
            catalogados.append((tc, CATALOGO["tcs"][str(tc["id"])]))
        else:
            no_catalogados.append(tc)
 
    print(f"[4] {len(catalogados)} TCs catalogados, {len(no_catalogados)} omitidos")
 
    if not catalogados:
        print(f"[ERROR] Ningun TC catalogado")
        sys.exit(1)
 
    ambiente_config = CATALOGO["ambientes"].get(ambiente_key)
    if not ambiente_config:
        print(f"[ERROR] Ambiente {ambiente_key} no configurado")
        sys.exit(1)
 
    apikey_check = os.environ.get(ambiente_config["apikey_env"])
    if not apikey_check:
        print(f"[ERROR] Variable {ambiente_config['apikey_env']} no configurada")
        sys.exit(1)
    print(f"[5] Host: {ambiente_config['host']}")
 
    print(f"\n[6] Quien ejecuta?")
    ejecutor = ""
    while True:
        nombre = input(f"  Nombre completo del ejecutor: ").strip()
        if len(nombre) < 5:
            print(f"  [ERROR] Nombre muy corto")
            continue
        if input(f"  Confirmas '{nombre}'? (s/n): ").strip().lower() == "s":
            ejecutor = nombre
            break
 
    print(f"\n[7] Resumen:")
    print(f"    HU/HT:     #{padre_id}")
    print(f"    TCs:       {len(catalogados)} catalogados")
    print(f"    Ambiente:  {ambiente_key.upper()}")
    print(f"    Ejecutor:  {ejecutor}")
    print(f"    Modo:      {'DRY-RUN' if dry_run else 'REAL'}")
 
    if input(f"\n    Continuar? (s/n): ").strip().lower() != "s":
        print("[CANCELADO]")
        sys.exit(0)
 
    if KARATE_DINAMICOS.exists():
        for f in KARATE_DINAMICOS.glob("*.feature"):
            f.unlink()
 
    resultados = []
    for i, (tc, tc_config) in enumerate(catalogados, 1):
        try:
            r = procesar_tc(tc, tc_config, ambiente_key, ambiente_config,
                            ejecutor, padre_id, dry_run, i, len(catalogados))
            resultados.append(r)
        except KeyboardInterrupt:
            print("\n[INTERRUMPIDO]")
            break
        except Exception as e:
            print(f"        [ERROR] {e}")
            resultados.append({"tc_id": tc["id"], "resultado": "ERROR"})
 
    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    p = sum(1 for r in resultados if r.get("resultado") == "PASS")
    f_count = sum(1 for r in resultados if r.get("resultado") == "FAIL")
    e_count = sum(1 for r in resultados if r.get("resultado") == "ERROR")
 
    for r in resultados:
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "ERROR": "[ERR]", "DRY-RUN": "[DRY]"}.get(r.get("resultado"), "?")
        print(f"  {icon} TC #{r['tc_id']} ({r.get('escenario', '?')}): {r.get('resultado')}")
 
    print()
    print(f"  Total: {len(resultados)} | PASS: {p} | FAIL: {f_count} | ERROR: {e_count}")
    print()
 
 
if __name__ == "__main__":
    main()
 