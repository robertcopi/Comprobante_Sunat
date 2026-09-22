from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """
    Modelo para registrar la auditoría y bitácora de acciones de usuarios sobre los recursos del sistema.
    Cumple con el estándar de registro obligatorio para acciones críticas y trazabilidad.
    """

    class AccionAuditoria(models.TextChoices):
        LOGIN = 'LOGIN', 'Inicio de Sesión (LOGIN)'
        LOGOUT = 'LOGOUT', 'Cierre de Sesión (LOGOUT)'
        REGISTRAR_COMPROBANTE = 'REGISTRAR_COMPROBANTE', 'Registro de Comprobante'
        EDITAR_COMPROBANTE = 'EDITAR_COMPROBANTE', 'Edición de Comprobante'
        ELIMINAR_COMPROBANTE = 'ELIMINAR_COMPROBANTE', 'Eliminación de Comprobante'
        IMPORTAR_ARCHIVO = 'IMPORTAR_ARCHIVO', 'Importación de Archivo'
        VALIDAR_COMPROBANTE = 'VALIDAR_COMPROBANTE', 'Validación Individual SUNAT'
        VALIDACION_MASIVA = 'VALIDACION_MASIVA', 'Validación Masiva SUNAT'
        EXPORTAR_REPORTE = 'EXPORTAR_REPORTE', 'Exportación de Reporte'
        OTRO = 'OTRO', 'Otra Acción'

    class ResultadoAuditoria(models.TextChoices):
        EXITOSO = 'EXITOSO', 'Exitoso'
        ERROR = 'ERROR', 'Error'
        FALLIDO = 'FALLIDO', 'Fallido'
        ADVERTENCIA = 'ADVERTENCIA', 'Advertencia'

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='registros_auditoria',
        verbose_name='Usuario'
    )
    accion = models.CharField(
        max_length=100,
        verbose_name='Acción',
        help_text='Identificador normalizado de la acción realizada'
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora'
    )
    objeto_afectado = models.CharField(
        max_length=255,
        verbose_name='Objeto Afectado'
    )
    id_objeto = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='ID del Objeto'
    )
    descripcion = models.TextField(
        verbose_name='Descripción'
    )
    resultado = models.CharField(
        max_length=50,
        choices=ResultadoAuditoria.choices,
        default=ResultadoAuditoria.EXITOSO,
        verbose_name='Resultado'
    )

    # Datos complementarios de seguridad
    ip_origen = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP Origen'
    )

    class Meta:
        verbose_name = 'Registro de Auditoría'
        verbose_name_plural = 'Registros de Auditoría'
        ordering = ['-fecha']
        indexes = [
            models.Index(fields=['usuario']),
            models.Index(fields=['accion']),
            models.Index(fields=['fecha']),
            models.Index(fields=['resultado']),
            models.Index(fields=['id_objeto']),
        ]

    def __str__(self):
        usuario_nombre = self.usuario.username if self.usuario else 'Sistema'
        return f"[{self.fecha.strftime('%d/%m/%Y %H:%M:%S')}] {usuario_nombre} - {self.accion} - {self.objeto_afectado} [{self.resultado}]"
