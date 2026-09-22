"""
Módulo de Integración con Servicios Oficiales de SUNAT.
Consulta Integrada de Validez de Comprobantes de Pago por Servicio Web (API REST / OAuth 2.0).

Este paquete aísla la comunicación con las APIs de SUNAT del resto de la aplicación.
"""

from .client import SunatClient, SunatValidationResult
from .constants import (
    CONDICION_DOMICILIO_RUC,
    ESTADO_CP,
    ESTADO_RUC,
    SUNAT_AUTH_URL_TEMPLATE,
    SUNAT_OAUTH_SCOPE,
    SUNAT_VALIDAR_URL_TEMPLATE,
    TIPOS_COMPROBANTE,
    traducir_estado_sistema,
)
from .exceptions import (
    SunatAuthError,
    SunatConfigError,
    SunatConnectionError,
    SunatError,
    SunatResponseError,
)

__all__ = [
    'SunatClient',
    'SunatValidationResult',
    'SunatError',
    'SunatConfigError',
    'SunatAuthError',
    'SunatConnectionError',
    'SunatResponseError',
    'ESTADO_CP',
    'ESTADO_RUC',
    'CONDICION_DOMICILIO_RUC',
    'TIPOS_COMPROBANTE',
    'SUNAT_AUTH_URL_TEMPLATE',
    'SUNAT_VALIDAR_URL_TEMPLATE',
    'SUNAT_OAUTH_SCOPE',
    'traducir_estado_sistema',
]
