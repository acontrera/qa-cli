Feature: TC #1177771 - HT #1083520
  Denegación de consulta cuando el token o los roles no están autorizados

  # ============================================================
  # GHERKIN ORIGINAL DEL TC (Azure DevOps):
  # ============================================================
  # Feature: Proteger el acceso al proxy de seguimiento de glosas para ERP EPS   Scenario: Rechazo de la operacion por autenticacion o autorizacion invalida     Given que el endpoint GET "/api/SeguimientoFacturaGlosa/ByIdFactura" es de acceso restringido para la ERP     And que la solicitud se realiza sin Bearer Token valido o con un usuario sin roles SIIFA_Admin, SIIFA_ERP, SIIFA_ERP_Gestor o SIIFA_ERP_Consulta     When el Integrador invoca el proxy de reconciliacion con IdFactura     Then el proxy debe denegar la operacion y propagar HTTP 401 cuando no exista autenticacion valida     And el proxy debe propagar HTTP 403 cuando el usuario autenticado no tenga permisos de rol     And se debe persistir un log tecnico de transaccion fallida con el motivo de rechazo para trazabilidad
  # ============================================================

  Background:
    * url 'https://api.labsura.com/siifaintegrador/v1/facturas-glosas/seguimientos/118524656'
    * def apikeyValor = 'INVALID_KEY_FOR_TESTING_ONLY'

  @tc1177771 @ht1083520 @auth_invalid
  Scenario: Denegación de consulta cuando el token o los roles no están autorizados

    # Configuracion del request
    * configure headers = { 'Content-Type': 'application/json', 'x-apikey': '#(apikeyValor)', 'Business-Line': '860005114' }

    # Ejecucion
    * method GET

    # Validaciones
    * print 'Status:', responseStatus
    * print 'Tiempo:', responseTime + 'ms'
    * def statusValidos = [401, 403]
    * assert statusValidos.indexOf(responseStatus) >= 0
    * assert responseTime < 3000
    * def opciones = ["Credencial", "Authentication", "Autenticaci\u00f3n", "Autorizaci\u00f3n", "unauthorized", "forbidden", "Invalid", "denied", "incorrecta", "faltante"]
    * def responseStr = (response + '').toLowerCase()
    * def encontrado = opciones.find(opt => responseStr.indexOf(opt.toLowerCase()) >= 0)
    * assert encontrado != null
    * print '[TC #1177771] PASS - status:', responseStatus
