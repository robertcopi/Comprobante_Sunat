"""
Cliente oficial de integración con los Servicios Web de SUNAT.
Consulta Integrada de Validez de Comprobantes de Pago (API REST / OAuth 2.0).

Cumple estrictamente con la normativa técnica y endpoints oficiales de SUNAT.
No almacena credenciales en código: se cargan desde settings.SUNAT_CONFIG o variables de entorno.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
import logging
import time
from typing import Any, Dict, List, Optional, Union

from django.conf import settings
import requests

from .constants import (
    CONDICION_DOMICILIO_RUC,
    ESTADO_CP,
    ESTADO_RUC,
    SUNAT_AUTH_URL_TEMPLATE,
    SUNAT_OAUTH_SCOPE,
    SUNAT_VALIDAR_URL_TEMPLATE,
    traducir_estado_sistema,
)
from .exceptions import (
    SunatAuthError,
    SunatConfigError,
    SunatConnectionError,
    SunatResponseError,
)

logger = logging.getLogger('services.sunat')


@dataclass
class SunatValidationResult:
    """Estructura estandarizada con el resultado de la validación ante SUNAT."""
    success: bool
    estado_cp: str = ''
    estado_cp_desc: str = ''
    estado_ruc: str = ''
    estado_ruc_desc: str = ''
    cond_domi_ruc: str = ''
    cond_domi_ruc_desc: str = ''
    observaciones: List[str] = field(default_factory=list)
    estado_sistema: str = 'ERROR_CONSULTA'
    mensaje: str = ''
    http_status: int = 0
    raw_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'estado_cp': self.estado_cp,
            'estado_cp_desc': self.estado_cp_desc,
            'estado_ruc': self.estado_ruc,
            'estado_ruc_desc': self.estado_ruc_desc,
            'cond_domi_ruc': self.cond_domi_ruc,
            'cond_domi_ruc_desc': self.cond_domi_ruc_desc,
            'observaciones': self.observaciones,
            'estado_sistema': self.estado_sistema,
            'mensaje': self.mensaje,
            'http_status': self.http_status,
            'raw_response': self.raw_response,
        }


class SunatClient:
    """
    Cliente para consumir la API oficial de SUNAT para Consulta Integrada de Comprobantes.

    Flujo:
    1. Autenticación OAuth 2.0 (client_credentials) contra api-seguridad.sunat.gob.pe
    2. Caching automático del token durante su tiempo de vida (expires_in).
    3. Consulta individual de comprobante contra api.sunat.gob.pe
    4. Interpretación y estandarización de códigos oficiales devueltos.
    """

    def __init__(
        self,
        ruc: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        modo: Optional[str] = None,
        timeout: int = 20,
        session: Optional[requests.Session] = None,
    ):
        # Cargar configuración desde parámetros o settings de Django
        config = getattr(settings, 'SUNAT_CONFIG', {})
        self.ruc = (ruc or config.get('RUC') or '').strip()
        self.client_id = (client_id or config.get('CLIENT_ID') or '').strip()
        self.client_secret = (client_secret or config.get('CLIENT_SECRET') or '').strip()
        self.modo = (modo or config.get('MODO') or 'BETA').upper()
        self.timeout = timeout
        self.session = session or requests.Session()

        # Cache interno del token en memoria
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def tiene_credenciales_configuradas(self) -> bool:
        """Verifica si las credenciales mínimas de API están configuradas."""
        return bool(self.ruc and self.client_id and self.client_secret)

    def _validar_credenciales(self) -> None:
        """Valida que existan las credenciales requeridas antes de realizar llamadas."""
        if not self.ruc:
            raise SunatConfigError("El RUC de la empresa consultante (SUNAT_RUC) no está configurado en .env.")
        if not self.client_id:
            raise SunatConfigError("El CLIENT_ID de SUNAT (SUNAT_CLIENT_ID) no está configurado en .env.")
        if not self.client_secret:
            raise SunatConfigError("El CLIENT_SECRET de SUNAT (SUNAT_CLIENT_SECRET) no está configurado en .env.")

    def obtener_token(self, force_refresh: bool = False) -> str:
        """
        Solicita o devuelve el token OAuth 2.0 almacenado en memoria si aún es válido.

        Endpoint oficial:
        POST https://api-seguridad.sunat.gob.pe/v1/clientesextranet/{client_id}/oauth2/token/
        """
        now = time.time()
        # Reutilizar token si aún le queda al menos 60 segundos de vigencia
        if not force_refresh and self._access_token and now < (self._token_expires_at - 60):
            return self._access_token

        self._validar_credenciales()

        url = SUNAT_AUTH_URL_TEMPLATE.format(client_id=self.client_id)
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        data = {
            'grant_type': 'client_credentials',
            'scope': SUNAT_OAUTH_SCOPE,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
        }

        try:
            logger.info("Solicitando nuevo token OAuth 2.0 a SUNAT...")
            response = self.session.post(url, data=data, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            logger.error(f"Falla de conexión al solicitar token a SUNAT: {e}")
            raise SunatConnectionError(f"No se pudo conectar con el servicio de autenticación de SUNAT: {e}")

        if response.status_code != 200:
            try:
                err_data = response.json()
            except Exception:
                err_data = {'raw_text': response.text}
            msg = f"Error en autenticación SUNAT (HTTP {response.status_code}): {err_data}"
            logger.error(msg)
            raise SunatAuthError(msg, raw_response=err_data, http_status=response.status_code)

        try:
            token_data = response.json()
            access_token = token_data.get('access_token')
            expires_in = int(token_data.get('expires_in', 3600))
        except Exception as e:
            raise SunatAuthError(f"Respuesta de token con formato inesperado: {e}", http_status=response.status_code)

        if not access_token:
            raise SunatAuthError("SUNAT no devolvió un access_token válido.", raw_response=token_data)

        self._access_token = access_token
        self._token_expires_at = time.time() + expires_in
        logger.info(f"Token SUNAT obtenido exitosamente. Vigencia: {expires_in} segundos.")
        return self._access_token

    def _formatear_fecha(self, fecha: Union[date, datetime, str]) -> str:
        """Formatea la fecha de emisión al formato oficial de SUNAT (dd/mm/yyyy)."""
        if isinstance(fecha, (date, datetime)):
            return fecha.strftime('%d/%m/%Y')
        if isinstance(fecha, str):
            fecha = fecha.strip()
            # Si viene en formato ISO (YYYY-MM-DD), convertir a DD/MM/YYYY
            if '-' in fecha and len(fecha) == 10:
                parts = fecha.split('-')
                if len(parts[0]) == 4:
                    return f"{parts[2]}/{parts[1]}/{parts[0]}"
            return fecha
        return str(fecha)

    def _formatear_monto(self, monto: Union[Decimal, float, int, str]) -> str:
        """Asegura que el monto tenga formato decimal con 2 dígitos (ej. '120.00')."""
        if isinstance(monto, (Decimal, float, int)):
            return f"{float(monto):.2f}"
        if isinstance(monto, str):
            try:
                return f"{float(monto.strip()):.2f}"
            except ValueError:
                return monto.strip()
        return "0.00"

    def validar_comprobante(
        self,
        num_ruc: str,
        cod_comp: str,
        numero_serie: str,
        numero: Union[int, str],
        fecha_emision: Union[date, datetime, str],
        monto: Union[Decimal, float, int, str],
    ) -> SunatValidationResult:
        """
        Realiza la consulta individual de validez de un comprobante ante SUNAT.

        Endpoint oficial:
        POST https://api.sunat.gob.pe/v1/contribuyente/contribuyentes/{ruc}/validarcomprobante

        Parámetros enviados a SUNAT:
        - numRuc: RUC del emisor (11 dígitos)
        - codComp: Tipo de comprobante ('01', '03', '07', '08', etc.)
        - numeroSerie: Serie alfanumérica de 4 caracteres
        - numero: Número correlativo
        - fechaEmision: Fecha en formato dd/mm/yyyy
        - monto: Monto total con dos decimales
        """
        # Formatear parámetros según estándar estricto
        payload = {
            "numRuc": str(num_ruc).strip(),
            "codComp": str(cod_comp).strip().zfill(2) if str(cod_comp).strip().isdigit() else str(cod_comp).strip(),
            "numeroSerie": str(numero_serie).strip().upper(),
            "numero": int(numero) if str(numero).strip().isdigit() else str(numero).strip(),
            "fechaEmision": self._formatear_fecha(fecha_emision),
            "monto": self._formatear_monto(monto),
        }

        token = self.obtener_token()
        url = SUNAT_VALIDAR_URL_TEMPLATE.format(ruc=self.ruc)
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

        try:
            logger.info(f"Consultando validez ante SUNAT: {payload['codComp']} {payload['numeroSerie']}-{payload['numero']} (RUC: {payload['numRuc']})")
            response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.RequestException as e:
            logger.error(f"Falla de red consultando comprobante en SUNAT: {e}")
            raise SunatConnectionError(f"Error de red o timeout conectando con el servicio de SUNAT: {e}")

        # Si el token expiró en el servidor (401), reintentar una sola vez con token forzado
        if response.status_code == 401:
            logger.warning("Token expirado en el servidor SUNAT (HTTP 401). Renovando token y reintentando...")
            token = self.obtener_token(force_refresh=True)
            headers['Authorization'] = f'Bearer {token}'
            try:
                response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            except requests.RequestException as e:
                raise SunatConnectionError(f"Error de red al reintentar tras renovación de token: {e}")

        # Procesar respuesta
        try:
            data_json = response.json()
        except Exception:
            data_json = {'raw_text': response.text}

        # Manejo de error de validación o respuesta no exitosa (400, 422, etc.)
        if response.status_code != 200:
            mensaje_err = data_json.get('msg') or data_json.get('message') or f"Error HTTP {response.status_code} de SUNAT"
            logger.warning(f"Respuesta con código de error de SUNAT (HTTP {response.status_code}): {mensaje_err}")
            return SunatValidationResult(
                success=False,
                estado_sistema='ERROR_CONSULTA',
                mensaje=str(mensaje_err),
                http_status=response.status_code,
                raw_response=data_json,
            )

        # Respuesta 200 OK: Extraer datos del comprobante
        # La estructura típica de SUNAT es {"success": true, "data": {...}, "message": "..."}
        inner_data = data_json.get('data', {}) if isinstance(data_json.get('data'), dict) else data_json

        estado_cp = str(inner_data.get('estadoCp', '')).strip()
        estado_ruc = str(inner_data.get('estadoRuc', '')).strip()
        cond_domi_ruc = str(inner_data.get('condDomiRuc', '')).strip()
        observaciones_raw = inner_data.get('observaciones', [])

        observaciones: List[str] = []
        if isinstance(observaciones_raw, list):
            observaciones = [str(o) for o in observaciones_raw if o]
        elif isinstance(observaciones_raw, str) and observaciones_raw:
            observaciones = [observaciones_raw]

        # Descripciones oficiales de códigos SUNAT
        estado_cp_desc = ESTADO_CP.get(estado_cp, f"Código {estado_cp} no reconocido")
        estado_ruc_desc = ESTADO_RUC.get(estado_ruc, f"Código {estado_ruc} no reconocido")
        cond_domi_ruc_desc = CONDICION_DOMICILIO_RUC.get(cond_domi_ruc, f"Código {cond_domi_ruc} no reconocido")

        # Interpretar estado interno del sistema
        estado_sistema = traducir_estado_sistema(
            estado_cp=estado_cp,
            estado_ruc=estado_ruc,
            cond_domi=cond_domi_ruc,
            observaciones=observaciones,
        )

        mensaje_exito = data_json.get('message') or f"Consulta realizada exitosamente. Estado: {estado_cp_desc}"

        return SunatValidationResult(
            success=True,
            estado_cp=estado_cp,
            estado_cp_desc=estado_cp_desc,
            estado_ruc=estado_ruc,
            estado_ruc_desc=estado_ruc_desc,
            cond_domi_ruc=cond_domi_ruc,
            cond_domi_ruc_desc=cond_domi_ruc_desc,
            observaciones=observaciones,
            estado_sistema=estado_sistema,
            mensaje=mensaje_exito,
            http_status=response.status_code,
            raw_response=data_json,
        )
