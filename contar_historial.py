# -*- coding: utf-8 -*-
"""
contar_historial.py - Cuenta los Casos de Prueba generados por el robot
a partir de los archivos TCs_HU_*.md del workspace (output/ e output/historial/).

Uso:
    py contar_historial.py
    py contar_historial.py --ruta "C:\\Sura\\AzureBoards-Workspace\\output"
    py contar_historial.py --detalle      -> muestra los titulos de cada escenario

Cada escenario cuenta una vez: se detecta por la linea que inicia con 'Given'
(los 'And' no se cuentan).
"""

import argparse
import glob
import os
import re
import sys

RUTA_DEFECTO = r"C:\Sura\AzureBoards-Workspace\output"

PATRON_GIVEN = re.compile(r"^\s*Given\b", re.IGNORECASE)
PATRON_TITULO = re.compile(r"^\s{0,3}(#{1,4}|Scenario:|Escenario:)\s*(.+)", re.IGNORECASE)
PATRON_HU = re.compile(r"TCs_HU_(\d+)", re.IGNORECASE)


def contar_archivo(ruta):
    """Devuelve (num_tcs, titulos) de un archivo .md."""
    with open(ruta, "r", encoding="utf-8", errors="replace") as f:
        lineas = f.readlines()

    num_tcs = sum(1 for l in lineas if PATRON_GIVEN.match(l))

    titulos = []
    for l in lineas:
        m = PATRON_TITULO.match(l)
        if m:
            titulo = m.group(2).strip()
            if titulo:
                titulos.append(titulo)
    return num_tcs, titulos


def main():
    parser = argparse.ArgumentParser(description="Cuenta TCs en los .md generados por qa-cli.")
    parser.add_argument("--ruta", default=RUTA_DEFECTO, help="Carpeta output del workspace")
    parser.add_argument("--detalle", action="store_true", help="Mostrar titulos de escenarios")
    args = parser.parse_args()

    if not os.path.isdir(args.ruta):
        print(f"[ERROR] No existe la carpeta: {args.ruta}")
        sys.exit(1)

    archivos = sorted(
        glob.glob(os.path.join(args.ruta, "**", "TCs_HU_*.md"), recursive=True)
    )
    if not archivos:
        print(f"[INFO] No se encontraron archivos TCs_HU_*.md en {args.ruta}")
        return

    total = 0
    hus = set()
    print("=" * 70)
    for ruta in archivos:
        nombre = os.path.basename(ruta)
        carpeta = os.path.relpath(os.path.dirname(ruta), args.ruta) or "."
        num, titulos = contar_archivo(ruta)
        total += num

        m = PATRON_HU.search(nombre)
        if m:
            hus.add(m.group(1))

        ubicacion = f" ({carpeta})" if carpeta != "." else ""
        print(f"{nombre}{ubicacion}  ->  {num} TC(s)")
        if args.detalle:
            for t in titulos:
                print(f"   - {t}")

    print("=" * 70)
    print(f"[TOTAL] {total} Casos de Prueba generados | {len(hus)} HU(s) | {len(archivos)} archivo(s)")

    # Alerta si algun archivo supera el limite de 4 TCs por HU (lineamiento Sura)
    excedidos = []
    for ruta in archivos:
        num, _ = contar_archivo(ruta)
        if num > 4:
            excedidos.append((os.path.basename(ruta), num))
    if excedidos:
        print("\n[ALERTA] Archivos que superan el maximo de 4 TCs por HU:")
        for nombre, num in excedidos:
            print(f"   - {nombre}: {num} TCs")


if __name__ == "__main__":
    main()
