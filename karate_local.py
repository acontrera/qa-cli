# -*- coding: utf-8 -*-
"""
karate_local.py - Ejecuta Karate en modo desarrollo, sin tocar ADO.

Util para validar que Karate funciona ANTES de integrar con ADO.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

KARATE_PROJECT = Path("C:/Sura/karate-glosas")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("feature", help="Nombre del feature, ej: tc_1177770")
    args = ap.parse_args()

    feature_name = args.feature.replace(".feature", "")
    feature_path = f"sura/glosas/dinamicos/{feature_name}.feature"

    apikey = os.environ.get("SURA_APIKEY_LAB", "")
    if not apikey:
        print("[ERROR] SURA_APIKEY_LAB no esta configurada")
        sys.exit(1)

    # Forzar JAVA_HOME correcto
    env = os.environ.copy()
    env["JAVA_HOME"] = "C:\\Program Files\\Eclipse Adoptium\\jdk-21.0.11.10-hotspot"
    java_bin = env["JAVA_HOME"] + "\\bin"
    maven_bin = "C:\\ProgramData\\chocolatey\\lib\\maven\\apache-maven-3.9.16\\bin"
    env["PATH"] = java_bin + ";" + maven_bin + ";" + env.get("PATH", "")

    cmd = f'mvn test -Dkarate.options=classpath:{feature_path} -DapikeyValida={apikey}'

    print(f"Ejecutando Karate (modo local, sin tocar ADO):")
    print(f"  Feature: {feature_path}")
    print()

    result = subprocess.run(
        cmd, cwd=str(KARATE_PROJECT), shell=True, env=env
    )

    print()
    if result.returncode == 0:
        print("[PASS] Karate ejecuto correctamente")
    else:
        print(f"[FAIL] Karate fallo (exit {result.returncode})")
    print()
    print(f"Reporte HTML: {KARATE_PROJECT}\\target\\karate-reports\\karate-summary.html")


if __name__ == "__main__":
    main()