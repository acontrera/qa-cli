# QA-CLI - Toolkit profesional de QA para Azure DevOps Sura

Comandos automatizados para gestionar Test Cases en Azure DevOps usando GitHub Copilot y ejecución de APIs con validaciones granulares.

## Capacidades principales

| Comando | Propósito |
|---|---|
| `qa-cli.py` | Crear Test Cases con Gherkin desde una HU/HT |
| `ejecutar_tcs.py` | Ejecutar TCs contra endpoints reales con evidencia automática |
| `crear_bug.py` | Crear bugs en ADO desde un TC fallido |
| `auditar_tcs.py` | Auditoría read-only de TCs existentes |
| `smoke_test_glosas.py` | Validación rápida de endpoints |

## Flujo de trabajo típico

Diseno:     py qa-cli.py <ID_HU>            -> Crea TCs en Gherkin
Auditoria:  py auditar_tcs.py <ID_HU>       -> Verifica estado actual
Ejecucion:  py ejecutar_tcs.py <ID_HU>      -> Corre los TCs + evidencia
Bug:        Si falla -> crear_bug.py automaticamente


## Ejecutor v3.0 - Catálogo granular por TC

Cada TC tiene su propia configuración en `tcs_catalog.json`:

- **Escenario**: happy_path, auth_invalid, happy_path_empty, etc.
- **Datos de prueba**: específicos por TC (factura con glosas, sin glosas, etc.)
- **Headers/apikey**: válida o inválida según el caso
- **Validaciones**: status code, tiempo, JSON, body contains, items mín/máx

### Cómo funciona

1. Valida que la HU/HT tenga TCs hijos
2. Valida que los TCs estén en formato Gherkin
3. Filtra solo los TCs catalogados (los no catalogados se omiten)
4. Pide nombre del ejecutor (obligatorio, con confirmación)
5. Por cada TC catalogado:
   - Cambia estado a "En progreso"
   - Ejecuta el endpoint con datos específicos del TC
   - Aplica validaciones del catálogo
   - Genera evidencia JSON
   - Sube attachment + comentario a ADO
   - PASS → "Cerrado" | FAIL → "Impedimento" + crear bug

## Conexión a Azure DevOps Sura

Ver `MANUAL_CONEXION.md` para guía paso a paso (Python sin admin, PAT, scopes).

## Configuración

1. Copiar `config.json.example` → `config.json` y completar con datos personales
2. Configurar variables de entorno:
   - `AZURE_DEVOPS_PAT` (PAT con scopes Work Items, Test Management)
   - `SURA_APIKEY_LAB` (API key del ambiente LAB)
   - `SURA_APIKEY_DEV` (API key del ambiente DEV, requiere VPN)
3. Agregar TCs al catálogo `tcs_catalog.json` con sus escenarios específicos

## Autor

**Andrés Felipe Contreras Muñoz**
QA / Quality Engineering Lead
Sofka @ Sura Colombia

Repo: https://github.com/acontrera/qa-cli