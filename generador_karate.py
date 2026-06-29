# -*- coding: utf-8 -*-
"""
generador_karate.py - Genera archivos .feature de Karate DSL desde TCs.

Este modulo se importa desde ejecutar_tcs.py para generar el entregable
de automatizacion Karate por cada TC ejecutado.

NO ejecuta Karate, solo GENERA el archivo .feature como artefacto.
"""

import json
from pathlib import Path


def generar_feature_karate(tc, tc_config, ambiente_config, ht_id,
                            datos_prueba, output_dir):
    """
    Genera un .feature de Karate y lo guarda en disco.

    Args:
        tc: dict del TC desde Azure DevOps
        tc_config: dict de configuracion del TC desde tcs_catalog.json
        ambiente_config: dict del ambiente (lab/dev)
        ht_id: ID de la HT padre
        datos_prueba: dict de datos de prueba globales del catalogo
        output_dir: Path donde guardar el .feature

    Returns:
        Path al .feature generado
    """
    tc_id = tc["id"]
    titulo = tc.get("fields", {}).get("System.Title", "")

    # Construir URL
    host = ambiente_config["host"]
    path = tc_config["path_template"]
    for var, key in tc_config.get("path_params", {}).items():
        valor = datos_prueba.get(key, key)
        path = path.replace("{" + var + "}", str(valor))

    url_completa = f"https://{host}{path}"
    query_params = tc_config.get("query_params", {})
    if query_params:
        qs = "&".join(f"{k}={v}" for k, v in query_params.items())
        url_completa = f"{url_completa}?{qs}"

    headers_extra = tc_config.get("headers_extra", {})
    business_line = headers_extra.get("Business-Line", "")

    body = tc_config.get("body")
    metodo = tc_config["method"].upper()
    escenario = tc_config.get("escenario", "default")
    apikey_tipo = tc_config.get("apikey_tipo", "valida")

    validaciones = tc_config.get("validaciones", {})
    status_esperado = validaciones.get("status_esperado", [200])
    tiempo_max = validaciones.get("tiempo_max_ms", 5000)
    body_contiene = validaciones.get("body_contiene", [])
    body_contiene_alguno = validaciones.get("body_contiene_alguno", [])

    titulo_safe = titulo.replace("'", "").replace('"', "")

    # Obtener Gherkin del TC desde la descripcion
    import re
    desc = tc.get("fields", {}).get("System.Description", "")
    gherkin = re.sub(r'<br\s*/?>', '\n', desc, flags=re.I)
    gherkin = re.sub(r'</p>', '\n', gherkin, flags=re.I)
    gherkin = re.sub(r'<[^>]+>', '', gherkin)
    gherkin = gherkin.replace('&nbsp;', ' ').replace('&amp;', '&')
    gherkin = gherkin.replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
    gherkin = gherkin.strip()

    gherkin_lines = [f"  # {line.strip()}" for line in gherkin.split("\n") if line.strip()]
    gherkin_comentarios = "\n".join(gherkin_lines)

    # Construir el feature
    lineas = []
    lineas.append(f"Feature: TC #{tc_id} - HT #{ht_id}")
    lineas.append(f"  {titulo_safe}")
    lineas.append("")
    lineas.append("  # ============================================================")
    lineas.append("  # GHERKIN ORIGINAL DEL TC (Azure DevOps):")
    lineas.append("  # ============================================================")
    lineas.append(gherkin_comentarios)
    lineas.append("  # ============================================================")
    lineas.append("")
    lineas.append("  Background:")
    lineas.append(f"    * url '{url_completa}'")

    # Apikey segun escenario
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
    lineas.append("    # Configuracion del request")
    headers_line = (
        "    * configure headers = "
        "{ 'Content-Type': 'application/json', "
        "'x-apikey': '#(apikeyValor)', "
        f"'Business-Line': '{business_line}' " + "}"
    )
    lineas.append(headers_line)

    # Body si POST/PUT
    if body and metodo in ("POST", "PUT", "PATCH"):
        lineas.append("")
        lineas.append("    # Request body")
        lineas.append("    * request")
        lineas.append('    """')
        body_str = json.dumps(body, indent=2)
        for body_line in body_str.split("\n"):
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

    contenido = "\n".join(lineas)

    # Guardar en disco
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    archivo = output_dir / f"tc_{tc_id}.feature"

    with open(archivo, "w", encoding="utf-8") as f:
        f.write(contenido)

    return archivo