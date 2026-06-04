# Instrucciones para GitHub Copilot - QA / Test Cases (Sura)

## Contexto
- Organizacion: SuraColombia
- Proyecto: Gerencia_Tecnologia
- Iniciativa: t-regulat_crossf-Iniciativa Normativa SIIFA
- Rol: QA / Quality Engineering Lead
- Stack: Serenity BDD + Screenplay + Java + Gradle + Gherkin

## Estructura jerarquica en Azure DevOps de Sura
HU (Historia de Usuario) o HT (Historia Tecnica)
└── Caso de Prueba (puede ser contenedor o directo)
├── Caso de Prueba hijo (con Gherkin completo)
└── ...

Cada Caso de Prueba contiene 1 Scenario Gherkin en el campo **Description** (NO en Steps).

## REFERENCIA REAL: Caso de Prueba #1147689 de Sura

Este es el formato exacto usado:

**Title:** Rechazo de procesamiento cuando la factura no tiene radicacion previa

**Description (aqui va el Gherkin completo):**
Feature: Validar radicacion previa antes de procesar devoluciones
Scenario: Evento de devolucion no procesado por ausencia de radicacion previa
Given que el broker de mensajeria tiene un evento de devolucion de factura enviado por SaludWeb
And el evento contiene datos validos de la factura (numeroFactura, idPrestador, fechaDevolucion, motivo)
And la factura no se encuentra previamente radicada en el sistema SIIFA
When el consumidor intenta procesar el evento de devolucion
Then no se debe persistir la informacion de la devolucion en la base de datos local
And se debe registrar un error indicando "Factura sin radicacion previa"
And el evento debe ser marcado para reproceso o enviado a una cola de errores (dead letter queue)
And se debe registrar la trazabilidad del intento fallido

**Campos custom:**
- Tipo de ejecucion: Manual
- Fase: Construccion
- Nivel de prueba: E2E

## REGLAS DE GENERACION DE TEST CASES

### 1. Title del TC

- En **ESPAÑOL** descriptivo
- Describe la VALIDACION principal (no el ID)
- Patron: `<accion> cuando <condicion>` o `<resultado> con <contexto>`
- Ejemplos buenos:
  - "Rechazo de procesamiento cuando la factura no tiene radicacion previa"
  - "Radicacion exitosa de factura con datos validos"
  - "Reintento automatico tras fallo temporal del servicio SIIFA"
- Ejemplos malos:
  - "TC_001" (sin descripcion)
  - "Probar el flujo" (vago)

### 2. Description del TC (donde va el Gherkin)

Formato exacto:
Feature: <descripcion en espanol del modulo o funcionalidad>
Scenario: <descripcion en espanol del caso especifico>
Given que <precondicion / contexto inicial en espanol>
And <precondicion adicional en espanol>
When <accion concreta en espanol>
Then <resultado esperado en espanol>
And <validacion adicional en espanol>

### 3. Indentacion EXACTA

- `Feature:` → 0 espacios al inicio (linea 1)
- Linea en blanco entre Feature y Scenario
- `Scenario:` → 0 espacios al inicio
- Steps (`Given/When/Then/And`) → **4 espacios** al inicio

### 4. Reglas de IDIOMA

- **Keywords en INGLES**: Feature, Scenario, Given, When, Then, And, But
- **TODO el resto en ESPAÑOL** con acentos correctos
- Usar comillas dobles para valores especificos: `"Factura sin radicacion previa"`

### 5. Estilo de redaccion de steps

- **Given usa "que"**: `Given que el broker tiene un evento...`
- **Steps atomicos**: una sola accion o validacion por step
- **Mencionar entidades reales de Sura**: SIIFA, SaludWeb, broker de mensajeria, RabbitMQ, ARL, EPS, dead letter queue, base de datos local, idPrestador, numeroFactura, fechaRadicacion, etc.
- **Multiples And** permitidos despues de Given y despues de Then
- **Maximo 2-3 When** consecutivos
- **NO mezclar** Given/When/Then en desorden

### 6. Campos custom por defecto (a menos que se indique otra cosa)

- **Tipo de ejecucion:** Manual (Automatizado si el TC va a Serenity BDD)
- **Fase:** Construccion
- **Nivel de prueba:**
  - E2E: pruebas end-to-end de flujo completo
  - Integracion: pruebas de integracion entre componentes/servicios
  - Unitaria: pruebas a nivel de codigo
  - Regresion: re-validacion de funcionalidad existente
  - Humo: smoke tests basicos
  - Aceptacion: pruebas con cliente / usuario final
- **Prioridad de caso:** Alta / Media / Baja segun criticidad

## FORMATO DE LA RESPUESTA DE COPILOT

Por cada Test Case generado, mostrar este bloque exacto:

```markdown
### TC #N: <Title en espanol>

**Title (Azure DevOps):**
<titulo en espanol>

**Description (pegar tal cual en el campo Description del TC):**

\`\`\`
Feature: <descripcion>

Scenario: <descripcion>
    Given que ...
    And ...
    When ...
    Then ...
    And ...
\`\`\`

**Campos custom:**
- Tipo de ejecucion: Manual / Automatizado
- Fase: Construccion
- Nivel de prueba: E2E / Integracion / Unitaria / Regresion / Humo / Aceptacion
- Prioridad de caso: Alta / Media / Baja

**Module / Functionality:** <modulo>

---
```

## Cobertura OBLIGATORIA por HU/HT

### Cantidad de Test Cases (REGLA DE SURA - ESTRICTA)

- **Historia de Usuario (HU):** MINIMO 3 TCs, IDEAL 3-4 TCs
- **Historia Tecnica (HT):** MINIMO 2 TCs, IDEAL 2-3 TCs
- **NO generar mas de 4 TCs por HU ni mas de 3 TCs por HT**
- **NO generar menos** del minimo (3 para HU, 2 para HT)

### Priorizacion de TCs cuando hay limites

Como tienes pocos TCs disponibles, priorizar SIEMPRE:

**Para HU (3-4 TCs):**
1. TC #1 OBLIGATORIO: Happy path principal (prioridad Alta) - cubre el flujo exitoso mas importante
2. TC #2 OBLIGATORIO: Escenario fallido / error mas critico (prioridad Alta) - validacion negativa clave
3. TC #3 OBLIGATORIO: Validacion de campos o edge case mas relevante (prioridad Media)
4. TC #4 OPCIONAL: Seguridad/permisos O trazabilidad O performance (prioridad Media/Baja)

**Para HT (2-3 TCs):**
1. TC #1 OBLIGATORIO: Funcionamiento exitoso del componente tecnico (prioridad Alta)
2. TC #2 OBLIGATORIO: Manejo de error / fallo del componente (prioridad Alta)
3. TC #3 OPCIONAL: Caso de borde tecnico o trazabilidad (prioridad Media)

### Estrategia para condensar criterios de aceptacion

Si la HU tiene **mas criterios que TCs permitidos**:

- **Agrupar criterios similares en un solo TC** (el Scenario puede tener multiples And que validen varios criterios)
- **Priorizar criterios de mayor impacto** (los que afectan dinero, datos sensibles, integraciones criticas)
- **Cada TC debe cubrir al menos 1 criterio de aceptacion** (no dejar criterios sin cubrir)
- **En el Title del TC**, reflejar el criterio principal que valida

### Que NO incluir si hay limite de TCs

- NO crear TCs para validaciones triviales (ej: campo obligatorio si ya esta cubierto en el happy path)
- NO crear TCs redundantes (mismo flujo con datos ligeramente distintos)
- NO crear TCs para escenarios poco probables o de muy bajo impacto
## Mapeo a criterios de aceptacion

- CADA criterio de aceptacion mapeado a >= 1 TC
- Reflejar el criterio en el Title del TC

## Secciones finales obligatorias en la respuesta

### A. Tabla de mapeo criterios -> TCs

| Criterio de aceptacion | TCs que lo cubren |
|---|---|
| Criterio 1 | TC #1, TC #3 |

### B. Recomendaciones de automatizacion

- Listar TCs candidatos a Serenity BDD + Screenplay (UI)
- TCs candidatos a RestAssured (API)
- TCs candidatos a JMeter (performance)
- Justificar (frecuencia, criticidad, ROI)

### C. Instrucciones para crear en Azure DevOps

Recordar al usuario:
1. Crear cada TC como hijo del Caso de Prueba padre (Link type: Child)
2. Copiar Title en espanol
3. **Pegar el Gherkin en el campo Description (NO en Steps)**
4. Llenar campos custom: Tipo de ejecucion, Fase, Nivel de prueba, Prioridad
5. Vincular al Parent correcto

## Reglas de calidad

- NO pasos vagos: "verificar que funcione", "validar correctamente"
- Cada step Gherkin debe ser atomico
- NO usar CSV para test cases ni datos de usuario
- Para APIs: mencionar endpoint, payload, response code, schema
- Para UI: mencionar elementos UI especificos
- Para mensajeria: mencionar colas, brokers, eventos especificos
- Para BD: mencionar tablas, registros, persistencia

## Stack tecnico

- Automation: Java + Gradle + Gherkin + Serenity BDD + Screenplay
- API: RestAssured
- Performance: JMeter
- Mobile: Appium
- CI/CD: GitLab + Docker
- Code quality: SonarQube
- Mensajeria: RabbitMQ
- Sistemas Sura: SIIFA, SaludWeb, ARL, EPS, OneSite, LandGorilla
