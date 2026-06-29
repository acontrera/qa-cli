Feature: TC #1177770 - HT #1083520
  Consulta exitosa de seguimientos de glosa con filtros técnicos por IdFactura

  # ============================================================
  # GHERKIN ORIGINAL DEL TC (Azure DevOps):
  # ============================================================
  # Feature: Consultar historial de glosas para reconciliacion tecnica en SIIFA   Scenario: Respuesta paginada exitosa con campos de trazabilidad y filtros opcionales     Given que el Componente Integrador SIIFA consume el proxy GET "/api/SeguimientoFacturaGlosa/ByIdFactura" con una factura previamente radicada     And que la peticion incluye el parametro obligatorio IdFactura y los filtros opcionales TieneRespuesta, IdSeguimientoTipoCodigoGlosa y Observacion     When el proxy orquesta la consulta hacia el servicio institucional de seguimiento de glosas     Then el sistema debe retornar HTTP 200 con una lista paginada de seguimientos de glosa asociados a la factura     And cada registro debe incluir idSeguimientoFacturaGlosa, codigo de glosa, valor, fecha de formulacion y estado de respuesta     And la respuesta debe contener unicamente los registros que cumplan los filtros tecnicos enviados     And se debe persistir un log tecnico de transaccion exitosa para el informe de trazabilidad de cuentas medicas
  # ============================================================

  Background:
    * url 'https://api.labsura.com/siifaintegrador/v1/facturas-glosas/seguimientos/118524656'
    * def apikeyValor = karate.properties['apikeyValida']

  @tc1177770 @ht1083520 @happy_path
  Scenario: Consulta exitosa de seguimientos de glosa con filtros técnicos por IdFactura

    # Configuracion del request
    * configure headers = { 'Content-Type': 'application/json', 'x-apikey': '#(apikeyValor)', 'Business-Line': '860005114' }

    # Ejecucion
    * method GET

    # Validaciones
    * print 'Status:', responseStatus
    * print 'Tiempo:', responseTime + 'ms'
    * def statusValidos = [200]
    * assert statusValidos.indexOf(responseStatus) >= 0
    * assert responseTime < 3000
    * match response + '' contains 'resultado'
    * print '[TC #1177770] PASS - status:', responseStatus
