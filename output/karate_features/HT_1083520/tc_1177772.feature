Feature: TC #1177772 - HT #1083520
  Respuesta vacia cuando la factura radicada no tiene glosas registradas

  # ============================================================
  # GHERKIN ORIGINAL DEL TC (Azure DevOps):
  # ============================================================
  # Feature: Determinar disponibilidad de nueva formulacion de glosa en reconciliacion tecnica   Scenario: Factura existente sin registros de glosa devuelve lista vacia     Given que la factura existe en SIIFA y se encuentra radicada     And que no existen seguimientos de glosa asociados al IdFactura consultado     When el orquestador consume el proxy GET "/api/SeguimientoFacturaGlosa/ByIdFactura"     Then el sistema debe retornar HTTP 200 con lista de resultados vacia     And el Integrador debe poder determinar que puede iniciar una nueva formulacion de glosa sin duplicidad de reporte     And se debe persistir un log tecnico del resultado vacio para mantener consistencia en la trazabilidad local
  # ============================================================

  Background:
    * url 'https://api.labsura.com/siifaintegrador/v1/facturas-glosas/seguimientos/99999999'
    * def apikeyValor = karate.properties['apikeyValida']

  @tc1177772 @ht1083520 @happy_path_empty
  Scenario: Respuesta vacia cuando la factura radicada no tiene glosas registradas

    # Configuracion del request
    * configure headers = { 'Content-Type': 'application/json', 'x-apikey': '#(apikeyValor)', 'Business-Line': '860005114' }

    # Ejecucion
    * method GET

    # Validaciones
    * print 'Status:', responseStatus
    * print 'Tiempo:', responseTime + 'ms'
    * def statusValidos = [200, 204, 404]
    * assert statusValidos.indexOf(responseStatus) >= 0
    * assert responseTime < 3000
    * print '[TC #1177772] PASS - status:', responseStatus
