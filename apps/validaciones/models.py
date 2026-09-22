from django.conf import settings
from django.db import models


class ValidacionSunat(models.Model):
    """
    Registro histórico de validaciones con SUNAT.
    Un comprobante puede tener múltiples validaciones para conservar el historial.
    """
    comprobante = models.ForeignKey(
        'comprobantes.Comprobante',
        on_delete=models.CASCADE,
        related_name='validaciones',
        verbose_name='Comprobante'
    )
    estado_sunat = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Estado SUNAT'
    )
    codigo_respuesta = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Código de Respuesta'
    )
    mensaje = models.TextField(
        blank=True,
        null=True,
        verbose_name='Mensaje de SUNAT'
    )
    fecha_validacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Validación'
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='validaciones_realizadas',
        verbose_name='Usuario que Realizó la Validación'
    )
    respuesta_sunat = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Respuesta Completa de SUNAT (JSON)'
    )

    class Meta:
        verbose_name = 'Validación SUNAT'
        verbose_name_plural = 'Validaciones SUNAT'
        ordering = ['-fecha_validacion']
        indexes = [
            models.Index(fields=['comprobante']),
            models.Index(fields=['fecha_validacion']),
        ]

    def __str__(self):
        return f"Validación #{self.id} de {self.comprobante} [{self.codigo_respuesta or 'Sin Código'}] ({self.fecha_validacion.strftime('%d/%m/%Y %H:%M')})"
