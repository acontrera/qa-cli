# -*- coding: utf-8 -*-
"""
ejecutar_tcs.py - Ejecutor de Test Cases con evidencia automatica.
v2.0 - Con validaciones explicitas, preview de response y ejecutor obligatorio.
 
Parte del toolkit qa-cli. Para una HU/HT dada:
  1. Valida que tenga TCs (sino: sugiere ejecutar qa-cli.py)
  2. Valida que TCs esten en Gherkin (sino: sugiere regenerar)
  3. Pide quien ejecuta (OBLIGATORIO, sin default)
  4. Ejecuta cada TC contra el endpoint catalogado
  5. Aplica validaciones explicitas (status, tiempo, json valido, body)
  6. Genera evidencia con preview de response
  7. Sube al TC: Discussion + Attachment
  8. PASS  -> estado "Cerrado"
  9. FAIL  -> estado "Impedimento" + invoca crear_bug.py interactivo
 
Uso:
    py ejecutar_tcs.py <ID_HU_o_HT> [--ambiente lab|dev] [--dry-run]
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
 
# ============================================================
# CONFIGURACION
# ============================================================
CONFIG_PATH = "config.json"
CATALOGO_PATH = "endpoints_catalog.json"
OUTPUT_DIR = Path("output") / "ejecuciones"
 
ESTADO_EN_PROGRESO = "En progreso"
ESTADO_PASS = "Cerrado"
ESTADO_FAIL = "Impedimento"
 
TIEMPO_MAX_MS = 3000
RESPONSE_PREVIEW_CHARS = 500
 
 
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
 
 
def obtener_wi(wid, expand_relations=False):
    expand = "&$expand=relations" if expand_relations else ""
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{wid}?api-version=7.1{expand}"
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
    ids = []
    for rel in rels:
        if rel.get("target") and rel.get("rel"):
            tid = rel["target"]["id"]
            if tid != parent_id:
                ids.append(tid)
    return ids
 
 
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
 
 
def es_gherkin(tc):
    desc = limpiar_html(tc.get("fields", {}).get("System.Description", ""))
    contenido = desc.lower()
    return ("feature:" in contenido and "scenario:" in contenido
            and "given" in contenido and "when" in contenido and "then" in contenido)
 
 
def validar_padre_y_tcs(padre_id):
    print(f"\n[1/6] Validando HU/HT #{padre_id}...")
 
    padre = obtener_wi(padre_id, expand_relations=False)
    if not padre:
        print(f"  [ERROR] No se encontro #{padre_id} en Azure DevOps")
        return None, None
 
    tipo = padre.get("fields", {}).get("System.WorkItemType", "")
    if tipo not in ("Historia", "User Story", "Product Backlog Item",
                    "Historia tecnica", "Historia técnica"):
        print(f"  [ERROR] Tipo no soportado: '{tipo}'. Pasa una HU o HT.")
        return None, None
 
    titulo = padre.get("fields", {}).get("System.Title", "")
    print(f"  [OK] {tipo}: {titulo[:60]}")
 
    print(f"\n[2/6] Buscando Test Cases hijos...")
    ids_descendientes = obtener_descendientes(padre_id)
 
    if not ids_descendientes:
        print(f"  [STOP] La {tipo} #{padre_id} NO tiene descendientes.")
        print(f"\n  ACCION REQUERIDA: Crea TCs primero con")
        print(f"     py qa-cli.py {padre_id}")
        return None, None
 
    descendientes = obtener_varios(ids_descendientes)
    tcs = [d for d in descendientes
           if d.get("fields", {}).get("System.WorkItemType") == "Caso de prueba"]
 
    if not tcs:
        print(f"  [STOP] No se encontraron Test Cases hijos.")
        print(f"  Ejecuta primero: py qa-cli.py {padre_id}")
        return None, None
 
    print(f"  [OK] {len(tcs)} Test Cases encontrados")
 
    tcs_validos = []
    tcs_legados = []
    for tc in tcs:
        titulo_tc = tc.get("fields", {}).get("System.Title", "")
        desc_tc = limpiar_html(tc.get("fields", {}).get("System.Description", ""))
        if titulo_tc.strip().lower() == "pruebas de calidad" and len(desc_tc) < 50:
            tcs_legados.append(tc)
        else:
            tcs_validos.append(tc)
 
    if tcs_legados:
        print(f"  [INFO] {len(tcs_legados)} contenedor(es) 'Pruebas de calidad' legados (se omiten)")
 
    if not tcs_validos:
        print(f"  [STOP] Todos los TCs son contenedores legados.")
        return None, None
 
    print(f"\n[3/6] Validando formato Gherkin en {len(tcs_validos)} TC(s)...")
    tcs_sin_gherkin = [tc for tc in tcs_validos if not es_gherkin(tc)]
 
    if tcs_sin_gherkin:
        print(f"  [STOP] {len(tcs_sin_gherkin)} TC(s) NO estan en formato Gherkin:")
        for tc in tcs_sin_gherkin:
            tit = tc.get("fields", {}).get("System.Title", "")[:60]
            print(f"    - TC #{tc['id']}: {tit}")
        print(f"\n  ACCION REQUERIDA: Regenera con py qa-cli.py {padre_id}")
        return None, None
 
    print(f"  [OK] Todos los TCs estan en Gherkin")
    return padre, tcs_validos
 
 
def buscar_endpoint(padre_id):
    mapeo = CATALOGO.get("mapeos", {}).get(str(padre_id))
    if not mapeo:
        print(f"  [STOP] La HU/HT #{padre_id} no esta catalogada en endpoints_catalog.json")
        return None
    return mapeo
 
 
def ejecutar_endpoint(mapeo, ambiente_config, apikey, dry_run=False):
    host = ambiente_config["host"]
    method = mapeo["method"]
    path = mapeo["path"]
    query = mapeo.get("query_params", {})
    headers_extra = mapeo.get("headers_extra", {})
    body = mapeo.get("body")
 
    url = f"https://{host}{path}"
    if query:
        qs = "&".join(f"{k}={v}" for k, v in query.items())
        url = f"{url}?{qs}"
 
    headers = {"Content-Type": "application/json", "x-apikey": apikey}
    headers.update(headers_extra)
 
    headers_masked = {k: ("***" if k.lower() == "x-apikey" else v) for k, v in headers.items()}
 
    request_info = {
        "method": method, "url": url, "headers": headers_masked, "body": body,
    }
 
    if dry_run:
        return {
            "status_code": None, "duracion_ms": 0,
            "body_response": "[DRY-RUN] No se ejecuto realmente",
            "headers_response": {}, "error": None, "request": request_info,
        }
 
    inicio = time.time()
    error = None
    status = None
    response_body = ""
    response_headers = {}
 
    try:
        if method == "GET":
            r = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            r = requests.post(url, headers=headers, json=body, timeout=30)
        elif method == "PUT":
            r = requests.put(url, headers=headers, json=body, timeout=30)
        elif method == "DELETE":
            r = requests.delete(url, headers=headers, timeout=30)
        else:
            error = f"Metodo no soportado: {method}"
            r = None
 
        if r is not None:
            status = r.status_code
            response_body = r.text  # Completo para validacion
            response_headers = dict(r.headers)
    except requests.exceptions.ConnectionError as e:
        error = f"Sin conexion: {e}"
    except requests.exceptions.Timeout:
        error = "Timeout (30s)"
    except Exception as e:
        error = str(e)
 
    duracion_ms = int((time.time() - inicio) * 1000)
 
    return {
        "status_code": status, "duracion_ms": duracion_ms,
        "body_response": response_body, "headers_response": response_headers,
        "error": error, "request": request_info,
    }
 
 
def aplicar_validaciones(resultado, mapeo):
    validaciones = []
    expected_statuses = mapeo.get("expected_status_pass", [200, 201])
 
    if resultado["error"]:
        validaciones.append({
            "nombre": "Conexion al endpoint",
            "esperado": "Sin errores de red/timeout",
            "obtenido": resultado["error"],
            "paso": False,
        })
        return validaciones
 
    validaciones.append({
        "nombre": "Conexion al endpoint",
        "esperado": "Sin errores de red/timeout",
        "obtenido": "Conexion exitosa",
        "paso": True,
    })
 
    status = resultado["status_code"]
    validaciones.append({
        "nombre": "HTTP Status esperado",
        "esperado": f"En {expected_statuses}",
        "obtenido": str(status),
        "paso": status in expected_statuses,
    })
 
    duracion = resultado["duracion_ms"]
    validaciones.append({
        "nombre": f"Tiempo de respuesta < {TIEMPO_MAX_MS}ms",
        "esperado": f"< {TIEMPO_MAX_MS}ms",
        "obtenido": f"{duracion}ms",
        "paso": duracion < TIEMPO_MAX_MS,
    })
 
    body = resultado["body_response"]
    if body and body.strip():
        try:
            json.loads(body)
            validaciones.append({
                "nombre": "Response es JSON valido",
                "esperado": "JSON parseable",
                "obtenido": "JSON valido",
                "paso": True,
            })
        except json.JSONDecodeError:
            validaciones.append({
                "nombre": "Response es JSON valido",
                "esperado": "JSON parseable",
                "obtenido": "No es JSON valido",
                "paso": False,
            })
 
        validaciones.append({
            "nombre": "Response body no vacio",
            "esperado": "Body con contenido",
            "obtenido": f"{len(body)} caracteres totales",
            "paso": len(body) > 0,
        })
 
    return validaciones
 
 
def todas_pasaron(validaciones):
    return all(v["paso"] for v in validaciones) if validaciones else False
 
 
def generar_evidencia(tc, mapeo, resultado_ejecucion, validaciones, ejecutor, ambiente, padre_id):
    fields = tc.get("fields", {})
    return {
        "metadata": {
            "tc_id": tc["id"],
            "tc_title": fields.get("System.Title", ""),
            "ht_id": padre_id,
            "ejecutor": ejecutor,
            "ambiente": ambiente,
            "timestamp": datetime.now().isoformat(),
            "fecha_legible": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        },
        "request": resultado_ejecucion["request"],
        "response": {
            "status_code": resultado_ejecucion["status_code"],
            "duracion_ms": resultado_ejecucion["duracion_ms"],
            "body": resultado_ejecucion["body_response"][:5000] if resultado_ejecucion["body_response"] else "",
            "body_full_length": len(resultado_ejecucion["body_response"]) if resultado_ejecucion["body_response"] else 0,
            "headers": resultado_ejecucion["headers_response"],
            "error": resultado_ejecucion["error"],
        },
        "expected": {
            "status_pass": mapeo.get("expected_status_pass", [200, 201]),
            "tiempo_max_ms": TIEMPO_MAX_MS,
        },
        "validaciones": validaciones,
        "resultado_global": "PASS" if todas_pasaron(validaciones) else "FAIL",
    }
 
 
def guardar_evidencia_local(evidencia, padre_id):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta = OUTPUT_DIR / f"HT_{padre_id}" / f"TC_{evidencia['metadata']['tc_id']}"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"evidencia_{ts}.json"
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(evidencia, f, indent=2, ensure_ascii=False)
    return archivo
 
 
def cambiar_estado_tc(tc_id, nuevo_estado):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{"op": "add", "path": "/fields/System.State", "value": nuevo_estado}]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    if r.status_code in (200, 201):
        return True, None
    return False, f"Status {r.status_code}: {r.text[:200]}"
 
 
def agregar_comentario(tc_id, texto):
    url = f"{BASE}/{PROJ}/_apis/wit/workItems/{tc_id}/comments?api-version=7.1-preview.4"
    payload = {"text": texto}
    r = requests.post(url, headers=h_json(), json=payload, timeout=15)
    return r.status_code in (200, 201)
 
 
def subir_attachment(archivo_path):
    nombre = Path(archivo_path).name
    url = f"{BASE}/{PROJ}/_apis/wit/attachments?fileName={nombre}&api-version=7.1"
    with open(archivo_path, "rb") as f:
        contenido = f.read()
 
    t = base64.b64encode(f":{PAT}".encode()).decode()
    headers = {
        "Authorization": f"Basic {t}",
        "Content-Type": "application/octet-stream",
    }
    r = requests.post(url, headers=headers, data=contenido, timeout=30)
    if r.status_code in (200, 201):
        return r.json().get("url"), None
    return None, f"Status {r.status_code}: {r.text[:200]}"
 
 
def vincular_attachment(tc_id, attachment_url, nombre):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{
        "op": "add",
        "path": "/relations/-",
        "value": {
            "rel": "AttachedFile",
            "url": attachment_url,
            "attributes": {"comment": f"Evidencia automatica - {nombre}"},
        }
    }]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)
 
 
def truncar_response(body, max_chars=RESPONSE_PREVIEW_CHARS):
    if not body:
        return "(vacio)"
    if len(body) <= max_chars:
        return body
    return body[:max_chars] + f"\n... [truncado, total: {len(body)} caracteres]"
 
 
def construir_comentario(evidencia, nombre_attachment):
    meta = evidencia["metadata"]
    resp = evidencia["response"]
    req = evidencia["request"]
    validaciones = evidencia["validaciones"]
    resultado_pass = evidencia["resultado_global"] == "PASS"
 
    badge = "PASS" if resultado_pass else "FAIL"
    icono = "&#9989;" if resultado_pass else "&#10060;"
    color = "#28a745" if resultado_pass else "#dc3545"
    status = resp["status_code"] if resp["status_code"] is not None else "N/A"
    duracion = resp["duracion_ms"] or 0
 
    filas_val = []
    for v in validaciones:
        check = "&#9989;" if v["paso"] else "&#10060;"
        nombre = str(v["nombre"]).replace("<", "&lt;").replace(">", "&gt;")
        obtenido = str(v["obtenido"]).replace("<", "&lt;").replace(">", "&gt;")
        filas_val.append(
            f"<tr><td style='padding:4px 8px;text-align:center;'>{check}</td>"
            f"<td style='padding:4px 8px;'>{nombre}</td>"
            f"<td style='padding:4px 8px;'><code>{obtenido}</code></td></tr>"
        )
    tabla_val = "\n".join(filas_val)
 
    body_preview = truncar_response(resp["body"]) if resp["body"] else "(sin body)"
    body_preview_html = body_preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
 
    html = f"""
<div style='font-family:Segoe UI,Arial,sans-serif;border-left:4px solid {color};padding:12px 18px;background:#f8f9fa;'>
    <h3 style='margin:0 0 12px 0;color:{color};'>{icono} {badge} - Ejecucion Automatica</h3>
 
    <table style='border-collapse:collapse;margin-bottom:12px;'>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ejecutor:</b></td><td>{meta['ejecutor']}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Fecha:</b></td><td>{meta['fecha_legible']}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ambiente:</b></td><td><b>{meta['ambiente'].upper()}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Endpoint:</b></td><td><code>{req['method']} {req['url']}</code></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Status HTTP:</b></td><td><b>{status}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Tiempo:</b></td><td>{duracion} ms</td></tr>
    </table>
 
    <h4 style='margin:8px 0 6px 0;color:#333;'>Validaciones aplicadas</h4>
    <table style='border-collapse:collapse;width:100%;margin-bottom:12px;border:1px solid #dee2e6;'>
        <thead>
            <tr style='background:#e9ecef;'>
                <th style='text-align:center;padding:6px 8px;width:40px;border-bottom:1px solid #dee2e6;'></th>
                <th style='text-align:left;padding:6px 8px;border-bottom:1px solid #dee2e6;'>Validacion</th>
                <th style='text-align:left;padding:6px 8px;border-bottom:1px solid #dee2e6;'>Resultado</th>
            </tr>
        </thead>
        <tbody>
            {tabla_val}
        </tbody>
    </table>
 
    <h4 style='margin:8px 0 6px 0;color:#333;'>Response preview (primeros {RESPONSE_PREVIEW_CHARS} chars)</h4>
    <pre style='background:#1e1e1e;color:#dcdcdc;padding:10px;border-radius:4px;font-size:12px;overflow-x:auto;max-height:200px;margin:0 0 10px 0;white-space:pre-wrap;'>{body_preview_html}</pre>
 
    <p style='margin-top:10px;font-size:13px;color:#666;'>
        Evidencia completa en attachment: <b>{nombre_attachment}</b>
    </p>
</div>
"""
    return html.strip()
 
 
def procesar_tc(tc, mapeo, ambiente_key, ambiente_config, apikey, ejecutor,
                padre_id, dry_run, idx, total):
    tc_id = tc["id"]
    titulo = tc.get("fields", {}).get("System.Title", "")
 
    print(f"\n[{idx}/{total}] TC #{tc_id}: {titulo[:60]}")
 
    if not dry_run:
        ok, err = cambiar_estado_tc(tc_id, ESTADO_EN_PROGRESO)
        if ok:
            print(f"        [OK] Estado -> {ESTADO_EN_PROGRESO}")
        else:
            print(f"        [WARN] No se pudo cambiar a 'En progreso': {err}")
 
    print(f"        [EXEC] {mapeo['method']} {mapeo['path'][:50]}...")
    resultado = ejecutar_endpoint(mapeo, ambiente_config, apikey, dry_run=dry_run)
 
    if not dry_run:
        validaciones = aplicar_validaciones(resultado, mapeo)
        pasaron = todas_pasaron(validaciones)
        total_v = len(validaciones)
        ok_v = sum(1 for v in validaciones if v["paso"])
        print(f"        [VALID] {ok_v}/{total_v} validaciones pasaron")
    else:
        validaciones = []
        pasaron = True
 
    evidencia = generar_evidencia(tc, mapeo, resultado, validaciones, ejecutor, ambiente_key, padre_id)
    archivo_evidencia = guardar_evidencia_local(evidencia, padre_id)
    print(f"        [EVID] {archivo_evidencia}")
 
    if dry_run:
        print(f"        [DRY-RUN] No se evalua PASS/FAIL")
        return {"tc_id": tc_id, "resultado": "DRY-RUN", "archivo": str(archivo_evidencia)}
    elif pasaron:
        print(f"        [PASS] HTTP {resultado['status_code']} ({resultado['duracion_ms']}ms)")
    else:
        print(f"        [FAIL] Alguna validacion fallo")
 
    print(f"        [UPLOAD] Subiendo evidencia a ADO...")
    nombre_attachment = archivo_evidencia.name
    attachment_url, err = subir_attachment(archivo_evidencia)
    if attachment_url:
        if vincular_attachment(tc_id, attachment_url, nombre_attachment):
            print(f"        [OK] Attachment vinculado")
        else:
            print(f"        [WARN] No se pudo vincular attachment")
    else:
        print(f"        [WARN] No se subio attachment: {err}")
 
    comentario_html = construir_comentario(evidencia, nombre_attachment)
    if agregar_comentario(tc_id, comentario_html):
        print(f"        [OK] Comentario agregado")
    else:
        print(f"        [WARN] No se pudo agregar comentario")
 
    estado_final = ESTADO_PASS if pasaron else ESTADO_FAIL
    ok, err = cambiar_estado_tc(tc_id, estado_final)
    if ok:
        print(f"        [OK] Estado final -> {estado_final}")
    else:
        print(f"        [WARN] No se pudo cambiar a '{estado_final}': {err}")
 
    if not pasaron:
        print()
        print(f"        +{'=' * 56}+")
        print(f"        |  TC #{tc_id} fallo. Crear bug en ADO?".ljust(63) + "|")
        print(f"        +{'=' * 56}+")
        resp = input(f"        Crear bug ahora? (s/n): ").strip().lower()
        if resp == "s":
            print(f"\n        Invocando crear_bug.py...")
            print(f"        " + "-" * 60)
            subprocess.run(["py", "crear_bug.py", "--tc", str(tc_id)])
            print(f"        " + "-" * 60)
        else:
            print(f"        [SKIP] No se creo bug. Puedes crearlo despues con:")
            print(f"               py crear_bug.py --tc {tc_id}")
 
    return {
        "tc_id": tc_id,
        "titulo": titulo,
        "resultado": "PASS" if pasaron else "FAIL",
        "status_code": resultado["status_code"],
        "duracion_ms": resultado["duracion_ms"],
        "archivo": str(archivo_evidencia),
    }
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("padre_id", type=int, help="ID de la HU o HT")
    ap.add_argument("--ambiente", choices=["dev", "lab"], default="lab")
    ap.add_argument("--dry-run", action="store_true", help="Simula sin ejecutar ni subir")
    args = ap.parse_args()
 
    padre_id = args.padre_id
    ambiente_key = args.ambiente
    dry_run = args.dry_run
 
    print()
    print("#" * 70)
    print(f"#  EJECUTOR DE TEST CASES v2.0")
    print(f"#  HU/HT: #{padre_id}")
    print(f"#  Ambiente: {ambiente_key.upper()}")
    print(f"#  Modo: {'DRY-RUN (simulacion)' if dry_run else 'EJECUCION REAL'}")
    print("#" * 70)
 
    padre, tcs_validos = validar_padre_y_tcs(padre_id)
    if not padre:
        sys.exit(1)
 
    print(f"\n[4/6] Buscando endpoint catalogado para HU/HT #{padre_id}...")
    mapeo = buscar_endpoint(padre_id)
    if not mapeo:
        sys.exit(1)
    print(f"  [OK] {mapeo['method']} {mapeo['path']}")
 
    ambiente_config = CATALOGO["ambientes"].get(ambiente_key)
    if not ambiente_config:
        print(f"[ERROR] Ambiente '{ambiente_key}' no existe")
        sys.exit(1)
 
    apikey = os.environ.get(ambiente_config["apikey_env"])
    if not apikey:
        print(f"[ERROR] Variable {ambiente_config['apikey_env']} no configurada")
        sys.exit(1)
 
    if ambiente_config.get("requiere_vpn"):
        print(f"  [INFO] Ambiente {ambiente_key.upper()} requiere VPN")
 
    # Ejecutor OBLIGATORIO sin default
    print(f"\n[5/6] Quien ejecuta?")
    ejecutor = ""
    while not ejecutor:
        ejecutor = input(f"  Nombre completo del ejecutor: ").strip()
        if not ejecutor:
            print(f"  [ERROR] El nombre del ejecutor es OBLIGATORIO para trazabilidad")
    print(f"  [OK] Ejecutor: {ejecutor}")
 
    print()
    print(f"[6/6] Resumen pre-ejecucion:")
    print(f"        - TCs a ejecutar:  {len(tcs_validos)}")
    print(f"        - Endpoint:        {mapeo['method']} {mapeo['path']}")
    print(f"        - Ambiente:        {ambiente_key.upper()} ({ambiente_config['host']})")
    print(f"        - Ejecutor:        {ejecutor}")
    print(f"        - Modo:            {'DRY-RUN' if dry_run else 'REAL (modifica ADO)'}")
    print()
    resp = input(f"  Continuar? (s/n): ").strip().lower()
    if resp != "s":
        print("[CANCELADO]")
        sys.exit(0)
 
    resultados = []
    for i, tc in enumerate(tcs_validos, 1):
        try:
            r = procesar_tc(tc, mapeo, ambiente_key, ambiente_config, apikey,
                            ejecutor, padre_id, dry_run, i, len(tcs_validos))
            resultados.append(r)
        except KeyboardInterrupt:
            print("\n[INTERRUMPIDO]")
            break
        except Exception as e:
            print(f"        [ERROR] {e}")
            resultados.append({"tc_id": tc["id"], "resultado": "ERROR", "error": str(e)})
 
    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    pass_count = sum(1 for r in resultados if r.get("resultado") == "PASS")
    fail_count = sum(1 for r in resultados if r.get("resultado") == "FAIL")
    err_count = sum(1 for r in resultados if r.get("resultado") == "ERROR")
 
    for r in resultados:
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "ERROR": "[ERR]", "DRY-RUN": "[DRY]"}.get(r.get("resultado"), "?")
        print(f"  {icon} TC #{r['tc_id']}: {r.get('resultado')}")
 
    print()
    print(f"  Total: {len(resultados)} | PASS: {pass_count} | FAIL: {fail_count} | ERROR: {err_count}")
    print(f"  Evidencia local: output/ejecuciones/HT_{padre_id}/")
    print()
 
 
if __name__ == "__main__":
    main()