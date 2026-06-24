"""
Smoke Test - Glosas Sura
Ejecuta los 6 endpoints del modulo de Glosas y guarda evidencia.

Uso:
    py smoke_test_glosas.py [dev|lab]

Ejemplos:
    py smoke_test_glosas.py dev     (requiere VPN)
    py smoke_test_glosas.py lab     (sin VPN)
"""

import requests
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# ============================================================
# CARGAR CATALOGO
# ============================================================
if not os.path.exists("endpoints_glosas.json"):
    print("[ERROR] No se encontro endpoints_glosas.json")
    sys.exit(1)

with open("endpoints_glosas.json", "r", encoding="utf-8") as f:
    catalogo = json.load(f)

# ============================================================
# AMBIENTE
# ============================================================
ambiente = sys.argv[1].lower() if len(sys.argv) > 1 else "lab"

if ambiente not in catalogo["ambientes"]:
    print(f"[ERROR] Ambiente '{ambiente}' no existe. Usa 'dev' o 'lab'")
    sys.exit(1)

amb_config = catalogo["ambientes"][ambiente]
host = amb_config["host"]
apikey = os.environ.get(amb_config["apikey_env"])

if not apikey:
    print(f"[ERROR] Variable {amb_config['apikey_env']} no esta definida.")
    print(f"        Configurala con SetEnvironmentVariable.")
    sys.exit(1)

# ============================================================
# CARPETA DE EVIDENCIA
# ============================================================
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_dir = Path("output") / "smoke_test" / f"{ambiente}_{timestamp}"
output_dir.mkdir(parents=True, exist_ok=True)

print()
print("#" * 70)
print(f"#  SMOKE TEST - GLOSAS SURA")
print(f"#  Ambiente: {amb_config['nombre']} ({host})")
print(f"#  Servicios: {len(catalogo['servicios'])}")
print(f"#  Evidencia: {output_dir}")
print("#" * 70)

if amb_config.get("requiere_vpn"):
    print()
    print("  [INFO] Este ambiente requiere VPN de Sura activa")
print()

# ============================================================
# EJECUTAR CADA SERVICIO
# ============================================================
resultados = []

for i, srv in enumerate(catalogo["servicios"], 1):
    print(f"[{i}/{len(catalogo['servicios'])}] HT #{srv['ht_id']}: {srv['nombre']}")

    # Construir URL
    url = f"https://{host}{srv['path']}"
    if srv["query_params"]:
        qs = "&".join(f"{k}={v}" for k, v in srv["query_params"].items())
        url = f"{url}?{qs}"

    # Headers
    headers = {
        "Content-Type": "application/json",
        "x-apikey": apikey,
    }
    headers.update(srv.get("headers_extra", {}))

    # Body
    body = srv.get("body")

    # Ejecutar
    inicio = time.time()
    error_msg = None
    status = None
    response_text = ""

    try:
        if srv["method"] == "GET":
            r = requests.get(url, headers=headers, timeout=30, verify=True)
        elif srv["method"] == "POST":
            r = requests.post(url, headers=headers, json=body, timeout=30, verify=True)
        elif srv["method"] == "PUT":
            r = requests.put(url, headers=headers, json=body, timeout=30, verify=True)
        elif srv["method"] == "DELETE":
            r = requests.delete(url, headers=headers, timeout=30, verify=True)
        else:
            error_msg = f"Metodo no soportado: {srv['method']}"
            r = None

        if r is not None:
            status = r.status_code
            response_text = r.text
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Sin conexion: {e}"
    except requests.exceptions.Timeout:
        error_msg = "Timeout (30s)"
    except Exception as e:
        error_msg = str(e)

    duracion_ms = int((time.time() - inicio) * 1000)

    # Resultado
    if error_msg:
        estado_visual = "[FAIL]"
        print(f"        {estado_visual} {error_msg}")
    elif 200 <= status < 300:
        estado_visual = f"[OK {status}]"
        print(f"        {estado_visual} ({duracion_ms}ms)")
    elif 400 <= status < 500:
        estado_visual = f"[WARN {status}]"
        print(f"        {estado_visual} ({duracion_ms}ms) - {response_text[:100]}")
    else:
        estado_visual = f"[FAIL {status}]"
        print(f"        {estado_visual} ({duracion_ms}ms)")

    # Guardar evidencia
    evidencia = {
        "ht_id": srv["ht_id"],
        "nombre": srv["nombre"],
        "ambiente": ambiente,
        "timestamp": datetime.now().isoformat(),
        "request": {
            "method": srv["method"],
            "url": url,
            "headers": {k: ("***" if k == "x-apikey" else v) for k, v in headers.items()},
            "body": body,
        },
        "response": {
            "status_code": status,
            "duracion_ms": duracion_ms,
            "body": response_text[:5000] if response_text else None,
            "error": error_msg,
        },
        "resultado": estado_visual,
    }

    archivo_evidencia = output_dir / f"HT_{srv['ht_id']}_evidencia.json"
    with open(archivo_evidencia, "w", encoding="utf-8") as f:
        json.dump(evidencia, f, indent=2, ensure_ascii=False)

    resultados.append({
        "ht_id": srv["ht_id"],
        "nombre": srv["nombre"],
        "estado": estado_visual,
        "status": status,
        "ms": duracion_ms,
        "error": error_msg,
    })

# ============================================================
# RESUMEN
# ============================================================
print()
print("=" * 70)
print("RESUMEN")
print("=" * 70)
print(f"  {'HT':<10} {'Servicio':<42} {'Estado':<14} {'Tiempo':<8}")
print("  " + "-" * 68)
for r in resultados:
    nombre = r["nombre"][:40]
    tiempo = f"{r['ms']}ms" if r["ms"] else "N/A"
    print(f"  #{r['ht_id']:<9} {nombre:<42} {r['estado']:<14} {tiempo:<8}")

# Estadisticas
ok = sum(1 for r in resultados if "OK" in r["estado"])
warn = sum(1 for r in resultados if "WARN" in r["estado"])
fail = sum(1 for r in resultados if "FAIL" in r["estado"])
total = len(resultados)

print()
print(f"  OK:   {ok}/{total}")
print(f"  WARN: {warn}/{total}  (4xx - posiblemente datos invalidos o esperado)")
print(f"  FAIL: {fail}/{total}")
print()
print(f"  Evidencia completa en: {output_dir.absolute()}")
print()

# Guardar resumen
resumen_path = output_dir / "_RESUMEN.json"
with open(resumen_path, "w", encoding="utf-8") as f:
    json.dump({
        "ambiente": ambiente,
        "timestamp": datetime.now().isoformat(),
        "estadisticas": {"ok": ok, "warn": warn, "fail": fail, "total": total},
        "resultados": resultados,
    }, f, indent=2, ensure_ascii=False)