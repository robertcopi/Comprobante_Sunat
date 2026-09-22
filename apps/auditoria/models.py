from django.conf import settings
from django.db import models


class RegistroAuditoria(models.Model):
    """
    Modelo para registrar la auditoría y bitácora de acciones de usuarios sobre los recursos del sistema.
    """
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
        verbose_name='Acción'
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha y Hora'
    )
    objeto_afectado = models.CharField(
        max_length=255,
        verbose_name='Objeto Afectado'
    )
    descripcion = models.TextField(
        verbose_name='Descripción'
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
        ]

    def __str__(self):
        usuario_nombre = self.usuario.username if self.usuario else 'Sistema'
        return f"[{self.fecha.strftime('%d/%m/%Y %H:%M:%S')}] {usuario_nombre} - {self.accion} - {self.objeto_afectado}"
