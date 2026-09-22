"""
Excepciones personalizadas para el servicio de integración con SUNAT.
"""


class SunatError(Exception):
    """Clase base para todos los errores generados en el módulo SUNAT."""
    def __init__(self, message: str, raw_response: dict = None, http_status: int = None):
        super().__init__(message)
        self.message = message
        self.raw_response = raw_response or {}
        self.http_status = http_status


class SunatConfigError(SunatError):
    """Lanzada cuando faltan credenciales requeridas o configuración en variables de entorno."""
    pass


class SunatAuthError(SunatError):
    """Lanzada cuando falla la autenticación OAuth 2.0 con SUNAT."""
    pass


class SunatConnectionError(SunatError):
    """Lanzada por errores de red, timeout o falla de comunicación con los servidores de SUNAT."""
    pass


class SunatResponseError(SunatError):
    """Lanzada cuando SUNAT devuelve una respuesta de error funcional (ej. HTTP 400, 422)."""
    pass
