# qa-cli — Toolkit de QA para Azure DevOps

Automatización de tareas QA sobre Azure DevOps (ADO) para proyectos de la Gerencia de Tecnología.

---

## Requisitos

- Python 3.x (`py` command)
- Variables de entorno configuradas:
  ```powershell
  $env:AZURE_DEVOPS_PAT = "tu-pat-de-ado"
  ```
- Dependencias:
  ```powershell
  py -m pip install requests anthropic --user
  ```

---

## Configuración

Edita `config.json` con tus datos:

```json
{
    "organization":           "SuraColombia",
    "project":                "Gerencia_Tecnologia",
    "user_email":             "tu.email@sura.com.co",
    "user_name":              "Tu Nombre Completo",
    "default_tipo_ejecucion": "Manual",
    "default_fase":           "Construcción",
    "default_nivel_prueba":   "Integración",
    "max_tcs_hu":             4,
    "max_tcs_ht":             3,
    "modulo_default":         "Salud Web",
    "output_dir":             "output"
}
```

---

## Scripts principales

### `qa-cli.py` — Generar y subir Test Cases

Genera Casos de Prueba en formato Gherkin a partir de una HU o HT y los sube a ADO.

```powershell
# Modo interactivo
py qa-cli.py

# Con ID de HU directo
py qa-cli.py --hu 123456

# Modo automático con IA (requiere ANTHROPIC_API_KEY)
py qa-cli.py --hu 123456 --auto
```

**Flujo:**
1. Lee la HU/HT desde ADO (título + descripción + criterios de aceptación)
2. Genera archivo `output/TCs_HU_XXXXXX.md` con los TCs en Gherkin
3. Valida calidad del Gherkin antes de subir
4. Sube los TCs a ADO como hijos de la HU/HT
5. Registra en `output/registro.csv`

---

### `crear_bug.py` — Crear Bugs desde un Test Case fallido

Crea un Bug en ADO leyendo el Gherkin de un TC existente. Deriva automáticamente
descripción, datos de prueba, pasos y resultado esperado del TC.

```powershell
# Modo interactivo
py crear_bug.py

# Con ID de TC directo
py crear_bug.py --tc 123456

# Dry-run (solo preview, no crea nada en ADO)
py crear_bug.py --tc 123456 --dry-run

# Completo por argumentos
py crear_bug.py --tc 123456 --dev "email@sura.com.co" --fallo "El endpoint retorna 500"
```

**Flujo:**
1. Lee el TC desde ADO (título + Gherkin + HT padre)
2. Hereda AreaPath e IterationPath de la HT padre
3. Pide: desarrollador (email), qué está fallando, severidad, bloqueante, nivel prueba, etapa, causa raíz, ID APM
4. Construye todos los campos del bug desde el Gherkin del TC:
   - `Given` → Datos de prueba
   - `When`  → Pasos para reproducir
   - `Then`  → Resultado esperado
5. Muestra preview completo y pide confirmación
6. Crea el Bug en ADO vinculado al TC
7. Registra en `output/registro_bugs.csv`

**Campos que llena automáticamente:**

| Campo ADO | Fuente |
|---|---|
| Título | `[BUG]` + título del TC |
| Descripción | Fallo + escenario + resultado esperado vs obtenido |
| Datos de prueba | Líneas `Given` del Gherkin |
| Pasos para reproducir | Fallo + líneas `When` del Gherkin |
| Resultado esperado | Líneas `Then` del Gherkin |
| Área / Iteración | Heredados de la HT padre |
| Atributo de calidad | Funcional (default) |
| Origen | Manual (default) |

---

### `contar_historial.py` — Contar TCs generados localmente

Cuenta los Casos de Prueba en los archivos `.md` del workspace.

```powershell
py contar_historial.py
py contar_historial.py --detalle
py contar_historial.py --ruta "C:\ruta\alternativa\output"
```

---

## Scripts de diagnóstico (`scripts/`)

Utilidades para descubrir campos y valores de ADO. Útiles cuando un campo
falla con error 400.

| Script | Propósito |
|---|---|
| `check_vals.py` | Lista valores permitidos de campos custom del Bug |
| `check_sev.py` | Consulta el campo Severity en ADO |
| `check_causa.py` | Consulta valores del campo Causa raíz |
| `check_user.py` | Verifica con qué usuario está autenticado el PAT |

```powershell
py scripts/check_vals.py
py scripts/check_user.py
```

---

## Estructura del workspace

```
AzureBoards-Workspace/
├── .github/                  # Instrucciones para GitHub Copilot
├── output/
│   ├── YYYY-MM-DD/           # TCs generados por fecha
│   ├── historial/            # TCs archivados
│   ├── work_items/           # Work items descargados
│   ├── registro.csv          # Historial de TCs subidos a ADO
│   └── registro_bugs.csv     # Historial de Bugs creados en ADO
├── scripts/                  # Utilidades de diagnóstico ADO
├── config.json               # Configuración del proyecto (no commitear)
├── config.json.example       # Plantilla de configuración
├── contar_historial.py       # Conteo local de TCs
├── crear_bug.py              # Creación de Bugs desde TCs
├── qa-cli.py                 # Generación y subida de TCs
├── qa.py                     # Módulo de utilidades QA
└── README.md
```

---

## Valores de referencia ADO (Sura)

### Bug — campos y valores permitidos

| Campo | Valores |
|---|---|
| Severidad | `1. Crítica` / `2. Media` / `3. Baja` |
| ¿Bloqueante? | `Sí` / `No` |
| Atributo de calidad | `Compatibilidad` / `Desempeño` / `Fiabilidad` / `Funcional` / `Usabilidad` |
| Nivel prueba | `Aceptación` / `E2E` / `Integración` / `Sistema` |
| Etapa de descubrimiento | `Certificación` / `Exploración` / `Post-implantación` / `Regresión` |
| Origen | `Automatizado` / `Híbrido` / `Manual` |

### Test Case — campos custom

| Campo | Reference Name |
|---|---|
| Tipo de ejecución | `Custom.886da9bd-...` |
| Prioridad de caso | `Custom.Prioridaddecaso` |

---

## Flujo recomendado por sprint

```
1. py qa-cli.py          → generar TCs para las HUs del sprint
2. py contar_historial.py → verificar conteo local
3. (ejecutar pruebas en ADO)
4. py crear_bug.py        → registrar bugs de TCs fallidos
```
