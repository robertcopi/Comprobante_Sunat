"""
Constantes oficiales del Servicio de Consulta Integrada de Validez
de Comprobantes de Pago de SUNAT (API REST / OAuth 2.0).

Basado en la documentación oficial y normativa técnica vigente de SUNAT.
"""

# URLs Oficiales de los Servicios de SUNAT
SUNAT_AUTH_URL_TEMPLATE = "https://api-seguridad.sunat.gob.pe/v1/clientesextranet/{client_id}/oauth2/token/"
SUNAT_VALIDAR_URL_TEMPLATE = "https://api.sunat.gob.pe/v1/contribuyente/contribuyentes/{ruc}/validarcomprobante"
SUNAT_OAUTH_SCOPE = "https://api.sunat.gob.pe/v1/contribuyente/contribuyentes"

# Catálogo oficial de tipos de comprobantes soportados en consulta
TIPOS_COMPROBANTE = {
    '01': 'Factura Electrónica',
    '03': 'Boleta de Venta Electrónica',
    '07': 'Nota de Crédito Electrónica',
    '08': 'Nota de Débito Electrónica',
    'R1': 'Recibo por Honorarios Electrónico',
    'R7': 'Nota de Crédito por Honorarios Electrónica',
}

# Códigos oficiales de estado del comprobante (estadoCp)
# Devuelto por el endpoint oficial validarcomprobante
ESTADO_CP = {
    '0': 'No existe',
    '1': 'Aceptado',
    '2': 'Anulado',
    '3': 'Autorizado (Físico con autorización de imprenta)',
    '4': 'No autorizado (Físico sin autorización de imprenta)',
}

# Códigos oficiales del estado del contribuyente emisor (estadoRuc)
ESTADO_RUC = {
    '00': 'Activo',
    '01': 'Baja provisional',
    '02': 'Baja provisional de oficio',
    '03': 'Suspensión temporal',
    '10': 'Baja definitiva',
    '11': 'Baja de oficio',
    '22': 'Inhabilitado',
}

# Códigos oficiales de la condición de domicilio fiscal del emisor (condDomiRuc)
CONDICION_DOMICILIO_RUC = {
    '00': 'Habido',
    '09': 'Pendiente',
    '11': 'Por verificar',
    '12': 'No habido',
    '20': 'No hallado',
}


def traducir_estado_sistema(estado_cp: str, estado_ruc: str = '00', cond_domi: str = '00', observaciones: list = None) -> str:
    """
    Interpreta los estados oficiales de SUNAT y los traduce a los estados
    internos del modelo Comprobante (ACEPTADO, OBSERVADO, RECHAZADO, ERROR_CONSULTA).

    Reglas de negocio tributario:
    1. Si estadoCp == '1' (Aceptado):
       - Si emisor está '00' (Activo) y domicilio '00' (Habido) sin observaciones -> ACEPTADO
       - Si emisor no está Activo, o no está Habido, o existen observaciones -> OBSERVADO
    2. Si estadoCp == '0' (No existe) o '2' (Anulado) o '4' (No autorizado) -> RECHAZADO
    3. Si estadoCp es desconocido o error de servicio -> ERROR_CONSULTA
    """
    if estado_cp == '1':
        es_emisor_valido = (estado_ruc == '00' and cond_domi == '00')
        tiene_observaciones = bool(observaciones and len(observaciones) > 0)
        if es_emisor_valido and not tiene_observaciones:
            return 'ACEPTADO'
        return 'OBSERVADO'

    elif estado_cp in ('0', '2', '4'):
        return 'RECHAZADO'

    elif estado_cp == '3':
        # Físico autorizado
        return 'ACEPTADO'

    return 'ERROR_CONSULTA'
