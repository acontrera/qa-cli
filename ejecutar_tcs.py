# -*- coding: utf-8 -*-
"""
ejecutar_tcs_v3.py - Ejecutor de Test Cases con catalogo GRANULAR por TC.

v3.0 - CAMBIO ARQUITECTONICO IMPORTANTE:
  - El catalogo ahora es por TC (no por HT)
  - Cada TC tiene sus datos especificos: happy/sad path, datos, validaciones
  - Si un TC no esta catalogado: lo OMITE (no ejecuta endpoint default)
  - Garantiza que la ejecucion CORRESPONDE al objetivo del TC

Uso:
    py ejecutar_tcs_v3.py <ID_HU_o_HT> [--ambiente lab|dev] [--dry-run]

Requiere:
    - tcs_catalog.json (catalogo granular por TC)
    - config.json
    - Variables de entorno: AZURE_DEVOPS_PAT, SURA_APIKEY_LAB o SURA_APIKEY_DEV
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
CATALOGO_PATH = "tcs_catalog.json"  # NUEVO catalogo granular
OUTPUT_DIR = Path("output") / "ejecuciones"

ESTADO_EN_PROGRESO = "En progreso"
ESTADO_PASS = "Cerrado"
ESTADO_FAIL = "Impedimento"

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
        print(f"        Crea primero el catalogo granular por TC")
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


# ============================================================
# AZURE DEVOPS - LECTURA
# ============================================================
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


# ============================================================
# VALIDACIONES
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


def es_gherkin(tc):
    desc = limpiar_html(tc.get("fields", {}).get("System.Description", ""))
    contenido = desc.lower()
    return ("feature:" in contenido and "scenario:" in contenido
            and "given" in contenido and "when" in contenido and "then" in contenido)


def validar_padre_y_tcs(padre_id):
    print(f"\n[1/7] Validando HU/HT #{padre_id}...")

    padre = obtener_wi(padre_id, expand_relations=False)
    if not padre:
        print(f"  [ERROR] No se encontro #{padre_id}")
        return None, None

    tipo = padre.get("fields", {}).get("System.WorkItemType", "")
    if tipo not in ("Historia", "User Story", "Product Backlog Item",
                    "Historia tecnica", "Historia técnica"):
        print(f"  [ERROR] Tipo no soportado: '{tipo}'")
        return None, None

    titulo = padre.get("fields", {}).get("System.Title", "")
    print(f"  [OK] {tipo}: {titulo[:60]}")

    print(f"\n[2/7] Buscando Test Cases hijos...")
    ids_descendientes = obtener_descendientes(padre_id)

    if not ids_descendientes:
        print(f"  [STOP] Sin descendientes. Ejecuta: py qa-cli.py {padre_id}")
        return None, None

    descendientes = obtener_varios(ids_descendientes)
    tcs = [d for d in descendientes
           if d.get("fields", {}).get("System.WorkItemType") == "Caso de prueba"]

    if not tcs:
        print(f"  [STOP] Sin Test Cases. Ejecuta: py qa-cli.py {padre_id}")
        return None, None

    print(f"  [OK] {len(tcs)} Test Cases encontrados")

    # Filtrar legados
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
        print(f"  [INFO] {len(tcs_legados)} contenedor(es) 'Pruebas de calidad' legados (omitidos)")

    if not tcs_validos:
        print(f"  [STOP] Todos legados")
        return None, None

    print(f"\n[3/7] Validando formato Gherkin...")
    tcs_sin_gherkin = [tc for tc in tcs_validos if not es_gherkin(tc)]

    if tcs_sin_gherkin:
        print(f"  [STOP] {len(tcs_sin_gherkin)} TC(s) NO estan en Gherkin:")
        for tc in tcs_sin_gherkin:
            tit = tc.get("fields", {}).get("System.Title", "")[:60]
            print(f"    - TC #{tc['id']}: {tit}")
        print(f"\n  ACCION: py qa-cli.py {padre_id}")
        return None, None

    print(f"  [OK] Todos los TCs estan en Gherkin")
    return padre, tcs_validos


def filtrar_tcs_catalogados(tcs_validos):
    """Separa TCs catalogados de los no catalogados (granularidad por TC)."""
    catalogados = []
    no_catalogados = []

    for tc in tcs_validos:
        tc_id_str = str(tc["id"])
        if tc_id_str in CATALOGO.get("tcs", {}):
            catalogados.append((tc, CATALOGO["tcs"][tc_id_str]))
        else:
            no_catalogados.append(tc)

    return catalogados, no_catalogados


# ============================================================
# RESOLUCION DE DATOS DE PRUEBA
# ============================================================
def resolver_path_params(template, path_params):
    """Reemplaza {variables} en el path con los datos del catalogo."""
    datos_prueba = CATALOGO.get("datos_prueba", {})
    resultado = template
    for var, key in path_params.items():
        valor = datos_prueba.get(key, key)
        resultado = resultado.replace("{" + var + "}", str(valor))
    return resultado


def obtener_apikey(tipo, ambiente_config):
    """Devuelve la apikey segun el tipo: 'valida' o 'invalida'."""
    if tipo == "valida":
        return os.environ.get(ambiente_config["apikey_env"])
    elif tipo == "invalida":
        # Usa un apikey claramente invalida para probar denegacion
        return "INVALID_KEY_FOR_TESTING_ONLY"
    elif tipo == "vacia":
        return ""
    else:
        return os.environ.get(ambiente_config["apikey_env"])


# ============================================================
# EJECUTOR DEL ENDPOINT
# ============================================================
def ejecutar_endpoint(tc_config, ambiente_config, dry_run=False):
    host = ambiente_config["host"]
    method = tc_config["method"]
    path = resolver_path_params(
        tc_config["path_template"],
        tc_config.get("path_params", {})
    )
    query = tc_config.get("query_params", {})
    headers_extra = tc_config.get("headers_extra", {})
    body = tc_config.get("body")

    apikey = obtener_apikey(tc_config.get("apikey_tipo", "valida"), ambiente_config)

    url = f"https://{host}{path}"
    if query:
        qs = "&".join(f"{k}={v}" for k, v in query.items())
        url = f"{url}?{qs}"

    headers = {"Content-Type": "application/json"}
    if apikey:
        headers["x-apikey"] = apikey
    headers.update(headers_extra)

    headers_masked = {
        k: ("***" if k.lower() == "x-apikey" and len(v) > 10 else v)
        for k, v in headers.items()
    }

    request_info = {
        "method": method,
        "url": url,
        "headers": headers_masked,
        "body": body,
        "escenario": tc_config.get("escenario", "default"),
    }

    if dry_run:
        return {
            "status_code": None,
            "duracion_ms": 0,
            "body_response": "[DRY-RUN]",
            "headers_response": {},
            "error": None,
            "request": request_info,
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
            response_body = r.text
            response_headers = dict(r.headers)
    except requests.exceptions.ConnectionError as e:
        error = f"Sin conexion: {e}"
    except requests.exceptions.Timeout:
        error = "Timeout (30s)"
    except Exception as e:
        error = str(e)

    duracion_ms = int((time.time() - inicio) * 1000)

    return {
        "status_code": status,
        "duracion_ms": duracion_ms,
        "body_response": response_body,
        "headers_response": response_headers,
        "error": error,
        "request": request_info,
    }


# ============================================================
# VALIDACIONES SEGUN EL TC ESPECIFICO
# ============================================================
def aplicar_validaciones(resultado, tc_config):
    """Aplica validaciones especificas del TC, no genericas."""
    validaciones = []
    val_config = tc_config.get("validaciones", {})

    # 1. Sin error de conexion
    if resultado["error"]:
        validaciones.append({
            "nombre": "Conexion al endpoint",
            "esperado": "Sin errores",
            "obtenido": resultado["error"],
            "paso": False,
        })
        return validaciones

    validaciones.append({
        "nombre": "Conexion al endpoint",
        "esperado": "Sin errores de red",
        "obtenido": "Conexion exitosa",
        "paso": True,
    })

    # 2. Status HTTP segun lo esperado por el TC
    status = resultado["status_code"]
    expected = val_config.get("status_esperado", [200])
    validaciones.append({
        "nombre": "HTTP Status segun TC",
        "esperado": f"En {expected}",
        "obtenido": str(status),
        "paso": status in expected,
    })

    # 3. Tiempo
    duracion = resultado["duracion_ms"]
    tmax = val_config.get("tiempo_max_ms", 3000)
    validaciones.append({
        "nombre": f"Tiempo < {tmax}ms",
        "esperado": f"< {tmax}ms",
        "obtenido": f"{duracion}ms",
        "paso": duracion < tmax,
    })

    body = resultado["body_response"] or ""

    # 4. JSON valido (si el TC lo pide)
    if val_config.get("body_es_json"):
        try:
            json.loads(body) if body else None
            validaciones.append({
                "nombre": "Response es JSON valido",
                "esperado": "JSON parseable",
                "obtenido": "JSON valido" if body else "Body vacio",
                "paso": bool(body),
            })
        except json.JSONDecodeError:
            validaciones.append({
                "nombre": "Response es JSON valido",
                "esperado": "JSON parseable",
                "obtenido": "No es JSON valido",
                "paso": False,
            })

    # 5. Body longitud minima
    if "body_min_length" in val_config:
        min_len = val_config["body_min_length"]
        validaciones.append({
            "nombre": f"Body longitud >= {min_len}",
            "esperado": f">= {min_len} chars",
            "obtenido": f"{len(body)} chars",
            "paso": len(body) >= min_len,
        })

    # 6. Body contiene textos especificos
    if "body_contiene" in val_config:
        for texto in val_config["body_contiene"]:
            validaciones.append({
                "nombre": f"Body contiene '{texto}'",
                "esperado": f"Contiene '{texto}'",
                "obtenido": "Contiene" if texto.lower() in body.lower() else "NO contiene",
                "paso": texto.lower() in body.lower(),
            })

    # 7. Body contiene alguno (para auth_invalid: 'unauthorized', 'forbidden', etc.)
    if "body_contiene_alguno" in val_config:
        opciones = val_config["body_contiene_alguno"]
        encontrado = None
        for texto in opciones:
            if texto.lower() in body.lower():
                encontrado = texto
                break
        validaciones.append({
            "nombre": f"Body contiene alguno de {opciones}",
            "esperado": f"Cualquiera de {opciones}",
            "obtenido": f"Encontrado '{encontrado}'" if encontrado else "No encontrado",
            "paso": encontrado is not None,
        })

    # 8. Items minimos/maximos en resultado
    if "body_min_items" in val_config or "body_max_items" in val_config:
        try:
            data = json.loads(body) if body else {}
            items = data.get("resultado", data) if isinstance(data, dict) else data
            if isinstance(items, list):
                n_items = len(items)
            else:
                n_items = 0

            if "body_min_items" in val_config:
                mn = val_config["body_min_items"]
                validaciones.append({
                    "nombre": f"Items >= {mn}",
                    "esperado": f">= {mn} items",
                    "obtenido": f"{n_items} items",
                    "paso": n_items >= mn,
                })

            if "body_max_items" in val_config:
                mx = val_config["body_max_items"]
                validaciones.append({
                    "nombre": f"Items <= {mx}",
                    "esperado": f"<= {mx} items",
                    "obtenido": f"{n_items} items",
                    "paso": n_items <= mx,
                })
        except Exception:
            pass

    return validaciones


def todas_pasaron(validaciones):
    return all(v["paso"] for v in validaciones) if validaciones else False


# ============================================================
# EVIDENCIA
# ============================================================
def generar_evidencia(tc, tc_config, resultado, validaciones, ejecutor, ambiente, padre_id):
    fields = tc.get("fields", {})
    body_full = resultado["body_response"] or ""
    return {
        "metadata": {
            "tc_id": tc["id"],
            "tc_title": fields.get("System.Title", ""),
            "ht_id": padre_id,
            "ejecutor": ejecutor,
            "ambiente": ambiente,
            "escenario": tc_config.get("escenario", "default"),
            "descripcion_caso": tc_config.get("descripcion", ""),
            "timestamp": datetime.now().isoformat(),
            "fecha_legible": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "version_ejecutor": "v3.0",
        },
        "request": resultado["request"],
        "response": {
            "status_code": resultado["status_code"],
            "duracion_ms": resultado["duracion_ms"],
            "body": body_full[:5000],
            "body_full_length": len(body_full),
            "headers": resultado["headers_response"],
            "error": resultado["error"],
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


# ============================================================
# AZURE DEVOPS - ESCRITURA
# ============================================================
def cambiar_estado_tc(tc_id, nuevo_estado):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{"op": "add", "path": "/fields/System.State", "value": nuevo_estado}]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    if r.status_code in (200, 201):
        return True, None
    return False, f"Status {r.status_code}"


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
    headers = {
        "Authorization": f"Basic {t}",
        "Content-Type": "application/octet-stream",
    }
    r = requests.post(url, headers=headers, data=contenido, timeout=30)
    if r.status_code in (200, 201):
        return r.json().get("url"), None
    return None, f"Status {r.status_code}"


def vincular_attachment(tc_id, attachment_url, nombre):
    url = f"{BASE}/{PROJ}/_apis/wit/workitems/{tc_id}?api-version=7.1"
    ops = [{
        "op": "add",
        "path": "/relations/-",
        "value": {
            "rel": "AttachedFile",
            "url": attachment_url,
            "attributes": {"comment": f"Evidencia v3.0 - {nombre}"},
        }
    }]
    r = requests.patch(url, headers=h_patch(), json=ops, timeout=15)
    return r.status_code in (200, 201)


# ============================================================
# COMENTARIO
# ============================================================
def truncar_response(body, max_chars=RESPONSE_PREVIEW_CHARS):
    if not body:
        return "(vacio)"
    total = len(body)
    if total <= max_chars:
        return body
    return body[:max_chars] + f"\n... [truncado, mostrados {max_chars} de {total} caracteres]"


def construir_comentario(evidencia, nombre_attachment):
    meta = evidencia["metadata"]
    resp = evidencia["response"]
    req = evidencia["request"]
    validaciones = evidencia["validaciones"]
    pasa = evidencia["resultado_global"] == "PASS"

    badge = "PASS" if pasa else "FAIL"
    icono = "&#9989;" if pasa else "&#10060;"
    color = "#28a745" if pasa else "#dc3545"
    status = resp["status_code"] if resp["status_code"] is not None else "N/A"
    duracion = resp["duracion_ms"] or 0

    filas_val = []
    for v in validaciones:
        check = "&#9989;" if v["paso"] else "&#10060;"
        nombre = str(v["nombre"]).replace("<", "&lt;").replace(">", "&gt;")
        esperado = str(v.get("esperado", "")).replace("<", "&lt;").replace(">", "&gt;")
        obtenido = str(v["obtenido"]).replace("<", "&lt;").replace(">", "&gt;")
        filas_val.append(
            f"<tr><td style='padding:4px 8px;text-align:center;'>{check}</td>"
            f"<td style='padding:4px 8px;'>{nombre}</td>"
            f"<td style='padding:4px 8px;font-size:11px;color:#666;'>{esperado}</td>"
            f"<td style='padding:4px 8px;'><code>{obtenido}</code></td></tr>"
        )
    tabla_val = "\n".join(filas_val)

    body_preview = truncar_response(resp["body"]) if resp["body"] else "(sin body)"
    body_preview_html = body_preview.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html = f"""
<div style='font-family:Segoe UI,Arial,sans-serif;border-left:4px solid {color};padding:12px 18px;background:#f8f9fa;'>
    <h3 style='margin:0 0 12px 0;color:{color};'>{icono} {badge} - Ejecucion Automatica v3.0</h3>

    <table style='border-collapse:collapse;margin-bottom:12px;'>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ejecutor:</b></td><td>{meta['ejecutor']}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Fecha:</b></td><td>{meta['fecha_legible']}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Ambiente:</b></td><td><b>{meta['ambiente'].upper()}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Escenario TC:</b></td><td><b>{meta['escenario']}</b> - {meta['descripcion_caso']}</td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Endpoint:</b></td><td><code>{req['method']} {req['url']}</code></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Status HTTP:</b></td><td><b>{status}</b></td></tr>
        <tr><td style='padding:3px 12px 3px 0;'><b>Tiempo:</b></td><td>{duracion} ms</td></tr>
    </table>

    <h4 style='margin:8px 0 6px 0;color:#333;'>Validaciones segun el Test Case</h4>
    <table style='border-collapse:collapse;width:100%;margin-bottom:12px;border:1px solid #dee2e6;'>
        <thead>
            <tr style='background:#e9ecef;'>
                <th style='text-align:center;padding:6px 8px;width:40px;border-bottom:1px solid #dee2e6;'></th>
                <th style='text-align:left;padding:6px 8px;border-bottom:1px solid #dee2e6;'>Validacion</th>
                <th style='text-align:left;padding:6px 8px;border-bottom:1px solid #dee2e6;'>Esperado</th>
                <th style='text-align:left;padding:6px 8px;border-bottom:1px solid #dee2e6;'>Obtenido</th>
            </tr>
        </thead>
        <tbody>
            {tabla_val}
        </tbody>
    </table>

    <h4 style='margin:8px 0 6px 0;color:#333;'>Response preview</h4>
    <pre style='background:#1e1e1e;color:#dcdcdc;padding:10px;border-radius:4px;font-size:12px;overflow-x:auto;max-height:200px;margin:0 0 10px 0;white-space:pre-wrap;'>{body_preview_html}</pre>

    <p style='margin-top:10px;font-size:13px;color:#666;'>
        Evidencia completa: <b>{nombre_attachment}</b>
    </p>
</div>
"""
    return html.strip()


# ============================================================
# FLUJO POR TC
# ============================================================
def procesar_tc(tc, tc_config, ambiente_key, ambiente_config, ejecutor,
                padre_id, dry_run, idx, total):
    tc_id = tc["id"]
    titulo = tc.get("fields", {}).get("System.Title", "")
    escenario = tc_config.get("escenario", "default")

    print(f"\n[{idx}/{total}] TC #{tc_id}: {titulo[:55]}")
    print(f"        Escenario: {escenario}")

    if not dry_run:
        ok, err = cambiar_estado_tc(tc_id, ESTADO_EN_PROGRESO)
        if ok:
            print(f"        [OK] Estado -> {ESTADO_EN_PROGRESO}")

    print(f"        [EXEC] {tc_config['method']} {tc_config['path_template'][:45]}...")
    resultado = ejecutar_endpoint(tc_config, ambiente_config, dry_run=dry_run)

    if not dry_run:
        validaciones = aplicar_validaciones(resultado, tc_config)
        pasaron = todas_pasaron(validaciones)
        ok_v = sum(1 for v in validaciones if v["paso"])
        print(f"        [VALID] {ok_v}/{len(validaciones)} validaciones pasaron")
    else:
        validaciones = []
        pasaron = True

    evidencia = generar_evidencia(tc, tc_config, resultado, validaciones, ejecutor, ambiente_key, padre_id)
    archivo_evidencia = guardar_evidencia_local(evidencia, padre_id)
    print(f"        [EVID] {archivo_evidencia}")

    if dry_run:
        print(f"        [DRY-RUN] No PASS/FAIL")
        return {"tc_id": tc_id, "resultado": "DRY-RUN"}
    elif pasaron:
        print(f"        [PASS] HTTP {resultado['status_code']} ({resultado['duracion_ms']}ms)")
    else:
        print(f"        [FAIL] Validacion no cumplida")

    print(f"        [UPLOAD] Subiendo evidencia a ADO...")
    nombre_attachment = archivo_evidencia.name
    attachment_url, err = subir_attachment(archivo_evidencia)
    if attachment_url and vincular_attachment(tc_id, attachment_url, nombre_attachment):
        print(f"        [OK] Attachment vinculado")
    else:
        print(f"        [WARN] Attachment: {err}")

    if agregar_comentario(tc_id, construir_comentario(evidencia, nombre_attachment)):
        print(f"        [OK] Comentario agregado")

    estado_final = ESTADO_PASS if pasaron else ESTADO_FAIL
    ok, err = cambiar_estado_tc(tc_id, estado_final)
    if ok:
        print(f"        [OK] Estado final -> {estado_final}")

    if not pasaron:
        print(f"\n        Crear bug en ADO?")
        resp = input(f"        Crear bug? (s/n): ").strip().lower()
        if resp == "s":
            subprocess.run(["py", "crear_bug.py", "--tc", str(tc_id)])
        else:
            print(f"        [SKIP] Puedes crearlo con: py crear_bug.py --tc {tc_id}")

    return {
        "tc_id": tc_id,
        "titulo": titulo,
        "resultado": "PASS" if pasaron else "FAIL",
        "escenario": escenario,
        "status_code": resultado["status_code"],
    }


# ============================================================
# MAIN
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("padre_id", type=int, help="ID de la HU o HT")
    ap.add_argument("--ambiente", choices=["dev", "lab"], default="lab")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    padre_id = args.padre_id
    ambiente_key = args.ambiente
    dry_run = args.dry_run

    print()
    print("#" * 70)
    print(f"#  EJECUTOR DE TEST CASES v3.0 (catalogo granular por TC)")
    print(f"#  HU/HT: #{padre_id}  |  Ambiente: {ambiente_key.upper()}")
    print(f"#  Modo: {'DRY-RUN' if dry_run else 'REAL'}")
    print("#" * 70)

    padre, tcs_validos = validar_padre_y_tcs(padre_id)
    if not padre:
        sys.exit(1)

    # NUEVO: filtrar solo los catalogados
    print(f"\n[4/7] Filtrando TCs catalogados...")
    catalogados, no_catalogados = filtrar_tcs_catalogados(tcs_validos)

    if not catalogados:
        print(f"  [STOP] Ningun TC esta catalogado en tcs_catalog.json")
        print(f"\n  TCs encontrados pero NO catalogados:")
        for tc in no_catalogados:
            print(f"    - TC #{tc['id']}: {tc.get('fields', {}).get('System.Title', '')[:55]}")
        print(f"\n  ACCION: Agrega estos TCs al catalogo tcs_catalog.json")
        sys.exit(1)

    print(f"  [OK] {len(catalogados)} TC(s) catalogado(s)")
    if no_catalogados:
        print(f"  [WARN] {len(no_catalogados)} TC(s) NO catalogado(s) - se OMITEN:")
        for tc in no_catalogados:
            print(f"    - TC #{tc['id']}: {tc.get('fields', {}).get('System.Title', '')[:55]}")

    # Ambiente
    print(f"\n[5/7] Configurando ambiente {ambiente_key.upper()}...")
    ambiente_config = CATALOGO["ambientes"].get(ambiente_key)
    if not ambiente_config:
        print(f"[ERROR] Ambiente '{ambiente_key}' no existe")
        sys.exit(1)

    apikey_check = os.environ.get(ambiente_config["apikey_env"])
    if not apikey_check:
        print(f"[ERROR] Variable {ambiente_config['apikey_env']} no configurada")
        sys.exit(1)
    print(f"  [OK] Host: {ambiente_config['host']}")

    # Ejecutor
    print(f"\n[6/7] Quien ejecuta?")
    ejecutor = ""
    while True:
        nombre_temp = ""
        while not nombre_temp:
            nombre_temp = input(f"  Nombre completo del ejecutor: ").strip()
            if not nombre_temp:
                print(f"  [ERROR] Obligatorio para trazabilidad")
            elif len(nombre_temp) < 5:
                print(f"  [ERROR] Muy corto. Nombre y apellido.")
                nombre_temp = ""

        print(f"\n  Vas a registrar como ejecutor: >>> {nombre_temp} <<<")
        if input(f"  Es correcto? (s/n): ").strip().lower() == "s":
            ejecutor = nombre_temp
            break
        print()
    print(f"  [OK] Ejecutor: {ejecutor}")

    # Resumen
    print(f"\n[7/7] Resumen pre-ejecucion:")
    print(f"        TCs a ejecutar (catalogados):  {len(catalogados)}")
    if no_catalogados:
        print(f"        TCs a OMITIR (sin catalogo):   {len(no_catalogados)}")
    print(f"        Ambiente:        {ambiente_key.upper()} ({ambiente_config['host']})")
    print(f"        Ejecutor:        {ejecutor}")
    print(f"        Modo:            {'DRY-RUN' if dry_run else 'REAL'}")
    print()

    if input(f"  Continuar? (s/n): ").strip().lower() != "s":
        print("[CANCELADO]")
        sys.exit(0)

    # Ejecutar
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

    # Resumen final
    print()
    print("=" * 70)
    print("RESUMEN FINAL")
    print("=" * 70)
    p = sum(1 for r in resultados if r.get("resultado") == "PASS")
    f = sum(1 for r in resultados if r.get("resultado") == "FAIL")
    e = sum(1 for r in resultados if r.get("resultado") == "ERROR")

    for r in resultados:
        icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "ERROR": "[ERR]", "DRY-RUN": "[DRY]"}.get(r.get("resultado"), "?")
        esc = r.get("escenario", "")
        print(f"  {icon} TC #{r['tc_id']} ({esc}): {r.get('resultado')}")

    print()
    print(f"  Total: {len(resultados)} | PASS: {p} | FAIL: {f} | ERROR: {e}")
    if no_catalogados:
        print(f"  Omitidos: {len(no_catalogados)} (sin catalogo - agrega al tcs_catalog.json)")
    print()


if __name__ == "__main__":
    main()
