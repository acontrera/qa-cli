# -*- coding: utf-8 -*-
"""Parche para corregir generar_feature_dinamico en ejecutar_karate.py"""

import re
from pathlib import Path

ARCHIVO = Path("ejecutar_karate.py")

if not ARCHIVO.exists():
    print(f"[ERROR] No se encontro {ARCHIVO}")
    raise SystemExit(1)

with open(ARCHIVO, "r", encoding="utf-8") as f:
    contenido = f.read()

nueva_funcion = """def generar_feature_dinamico(tc, tc_config, ambiente_config, ht_id):
    \"\"\"Genera un .feature de Karate dinamicamente para este TC especifico.\"\"\"
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

    gherkin_lines = [f"  # {line}" for line in gherkin.split("\\n") if line.strip()]
    gherkin_comentarios = "\\n".join(gherkin_lines)

    metodo = tc_config["method"]
    escenario = tc_config.get("escenario", "default")
    apikey_tipo = tc_config.get("apikey_tipo", "valida")

    titulo_safe = titulo.replace("'", "").replace('"', '')

    lineas = []
    lineas.append(f"Feature: TC #{tc_id} - HT #{ht_id} - {titulo_safe[:80]}")
    lineas.append("")
    lineas.append("  Background:")
    lineas.append(f"    * url '{url_completa}'")

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
    headers_line = "    * configure headers = { 'Content-Type': 'application/json', 'x-apikey': '#(apikeyValor)', 'Business-Line': '" + business_line + "' }"
    lineas.append(headers_line)
    lineas.append("")

    if body_json_str and metodo.upper() in ("POST", "PUT", "PATCH"):
        lineas.append("    # Request body desde catalogo")
        lineas.append("    * request")
        lineas.append('    """')
        for body_line in body_json_str.split("\\n"):
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

    return "\\n".join(lineas)


"""

patron = re.compile(
    r"def generar_feature_dinamico\(tc, tc_config, ambiente_config, ht_id\):.*?(?=\n# =)",
    re.DOTALL
)

if patron.search(contenido):
    nuevo_contenido = patron.sub(nueva_funcion, contenido)
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        f.write(nuevo_contenido)
    print(f"[OK] Funcion generar_feature_dinamico actualizada en {ARCHIVO}")
    print("[OK] Sintaxis Karate corregida")
    print("")
    print("Siguiente paso:")
    print("  py ejecutar_karate.py 1083520 --ambiente lab --dry-run")
else:
    print(f"[ERROR] No se encontro la funcion en {ARCHIVO}")