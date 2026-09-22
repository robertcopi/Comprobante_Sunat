import logging
import re
from typing import Any, Optional
from django.conf import settings
from .models import RegistroAuditoria

logger = logging.getLogger('auditoria')

# Patrones de datos confidenciales y sensibles que NUNCA deben registrarse
PATRONES_SENSIBLES = [
    (re.compile(r'(password|contrase[ñn]a|clave)\s*[:=]\s*[\'"\w\-\.@!#$%^&*]+', re.IGNORECASE), r'\1=[PROTEGIDO]'),
    (re.compile(r'(access_token|token|refresh_token)\s*[:=]\s*[\'"\w\-\.@!#$%^&*]+', re.IGNORECASE), r'\1=[PROTEGIDO]'),
    (re.compile(r'(client_secret|client_id|secret)\s*[:=]\s*[\'"\w\-\.@!#$%^&*]+', re.IGNORECASE), r'\1=[PROTEGIDO]'),
    (re.compile(r'bearer\s+[a-zA-Z0-9\-_.]+', re.IGNORECASE), 'Bearer [PROTEGIDO]'),
    (re.compile(r'eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}', re.IGNORECASE), '[JWT_PROTEGIDO]'),
]


def sanitizar_texto(texto: Any) -> str:
    """
    Purga cualquier contraseña, token SUNAT, client secret, credencial o dato sensible del texto.
    """
    if texto is None:
        return ''
    cadena = str(texto)
    for patron, reemplazo in PATRONES_SENSIBLES:
        cadena = patron.sub(reemplazo, cadena)
    return cadena


def obtener_ip_cliente(request: Any) -> Optional[str]:
    """
    Extrae la dirección IP real del cliente desde la petición HTTP.
    """
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')

    # Validar formato IPv4/IPv6 básico para evitar error de GenericIPAddressField
    if ip and (' ' in ip or len(ip) > 45):
        ip = ip.split()[0]
    return ip


class AuditoriaService:
    """
    Servicio centralizado para registrar eventos de auditoría y bitácora con sanitización obligatoria.
    """

    @classmethod
    def registrar(
        cls,
        usuario: Any = None,
        accion: str = RegistroAuditoria.AccionAuditoria.OTRO,
        objeto_afectado: str = '',
        id_objeto: Optional[str] = None,
        descripcion: str = '',
        resultado: str = RegistroAuditoria.ResultadoAuditoria.EXITOSO,
        ip_origen: Optional[str] = None,
        request: Any = None
    ) -> Optional[RegistroAuditoria]:
        """
        Crea un registro de auditoría sanitizado.
        Garantiza que errores en el registro de auditoría nunca interrumpan la operación principal.
        """
        try:
            # Resolver IP
            ip_final = ip_origen or obtener_ip_cliente(request)

            # Sanitizar descripciones y nombres de objetos
            objeto_sanitizado = sanitizar_texto(objeto_afectado)[:255]
            desc_sanitizada = sanitizar_texto(descripcion)
            id_objeto_str = str(id_objeto)[:100] if id_objeto is not None else None

            # Normalizar resultado
            resultado_final = (resultado or 'EXITOSO').upper()
            if resultado_final not in [r[0] for r in RegistroAuditoria.ResultadoAuditoria.choices]:
                resultado_final = RegistroAuditoria.ResultadoAuditoria.EXITOSO

            # Normalizar usuario autenticado si se pasó request
            usuario_final = usuario
            if usuario_final is None and request and hasattr(request, 'user') and request.user.is_authenticated:
                usuario_final = request.user

            return RegistroAuditoria.objects.create(
                usuario=usuario_final,
                accion=accion,
                objeto_afectado=objeto_sanitizado,
                id_objeto=id_objeto_str,
                descripcion=desc_sanitizada,
                resultado=resultado_final,
                ip_origen=ip_final
            )
        except Exception as e:
            logger.error(f"Error registrando auditoría [{accion}]: {e}", exc_info=True)
            return None
