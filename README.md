# QA-CLI - Fábrica automatizada de Test Cases para Azure DevOps

Comando único en Python para generar Test Cases en Azure DevOps usando GitHub Copilot, siguiendo formato Gherkin BDD.

> Creado por un QA Lead con 15+ años de experiencia para acelerar la generación de test cases en equipos ágiles trabajando con Azure DevOps.

## Características

- 🤖 Genera test cases usando GitHub Copilot (sin pagar APIs adicionales)
- 📋 Formato Gherkin BDD (Given/When/Then) estándar
- 🔗 Sube automáticamente los TCs a Azure DevOps como hijos de la HU/HT
- 👤 Multi-usuario (cada miembro del equipo con su propia configuración)
- 📦 Procesamiento individual o en lote
- ⚡ Reducción de ~85% en tiempo vs creación manual

## Requisitos previos

- Python 3.10+
- VS Code + GitHub Copilot Chat
- Acceso a Azure DevOps
- PAT (Personal Access Token) con permisos: Work Items, Test Management

## Instalación

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/qa-cli.git
cd qa-cli
```

### 2. Instalar dependencias

```bash
pip install requests --user
```

### 3. Configurar tu usuario

Copia la plantilla y edítala con tus datos:

```bash
cp config.json.example config.json
```

Abre `config.json` y completa:
- `organization`: tu organización en Azure DevOps
- `project`: tu proyecto
- `user_email`: tu correo corporativo
- `user_name`: tu nombre completo

### 4. Configurar PAT como variable de entorno

```powershell
# Windows PowerShell
[System.Environment]::SetEnvironmentVariable("AZURE_DEVOPS_PAT", "tu-pat-aqui", "User")
```

```bash
# Linux/Mac
export AZURE_DEVOPS_PAT="tu-pat-aqui"
```

Cierra y reabre la terminal.

### 5. Configurar las instrucciones de Copilot

Asegúrate de tener el archivo `.github/copilot-instructions.md` con las reglas de formato Gherkin de tu organización.

## Uso

### Procesar una HU/HT

```bash
py qa-cli.py 12345
```

### Procesar varias HUs en lote

```bash
py qa-cli.py 12345 12346 12347
```

### Flujo automático
[1/4] Descarga la HU/HT de Azure DevOps
[2/4] Prepara el prompt para Copilot (en tu portapapeles)
[3/4] PAUSA: pegas en Copilot Chat y dejas que genere los TCs
[4/4] Sube los TCs a Azure DevOps (asignados a ti)

## Scripts disponibles

| Script | Propósito |
|---|---|
| `qa-cli.py` | ⭐ Comando principal todo-en-uno |
| `qa.py` | Descarga una HU/work item individual |
| `subir_tcs.py` | Sube TCs desde un .md (uso aislado) |
| `asignar_tcs.py` | Asigna TCs a un usuario |
| `reparar_vinculos.py` | Mueve TCs entre padres |
| `descubrir_campos.py` | Debug: lista campos custom |
| `descubrir_valores.py` | Debug: lista valores permitidos |

## Estructura de un Test Case generado

Cada TC se crea como hijo directo de la HU/HT con:

- **Title**: descriptivo en español
- **Description**: bloque Gherkin completo
  - Feature: descripción del módulo
  - Scenario: caso específico
  - Steps: Given/When/Then/And (keywords inglés, contenido español)
- **Campos custom**: Tipo ejecución, Fase, Nivel de prueba, Prioridad

## Reglas aplicadas

- HU: máximo 4 TCs
- HT: máximo 3 TCs
- Asignación automática al usuario configurado
- Vinculación como hijo directo (no a través de contenedores intermedios)

## Contribuir

Pull requests bienvenidos. Para cambios mayores, abre un issue primero para discutir el cambio.

## Licencia

MIT

## Autor

Andrés Felipe Contreras Muñoz - QA / Quality Engineering Lead
