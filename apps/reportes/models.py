from django.conf import settings
from django.db import models


class ReporteGenerado(models.Model):
    """
    Registro histórico de reportes emitidos (Excel, PDF) y sus criterios de filtrado.
    """
    class TipoReporte(models.TextChoices):
        EXCEL = 'EXCEL', 'Excel (.xlsx)'
        PDF = 'PDF', 'PDF (.pdf)'

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reportes_generados',
        verbose_name='Usuario Solicitante'
    )
    tipo_reporte = models.CharField(
        max_length=10,
        choices=TipoReporte.choices,
        verbose_name='Tipo de Reporte'
    )
    titulo = models.CharField(
        max_length=200,
        verbose_name='Título / Nombre del Reporte'
    )
    filtros_aplicados = models.JSONField(
        default=dict,
        blank=True,
        verbose_name='Filtros Aplicados'
    )
    archivo = models.FileField(
        upload_to='reportes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Archivo Generado'
    )
    fecha_generacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Generación'
    )

    class Meta:
        verbose_name = 'Reporte Generado'
        verbose_name_plural = 'Reportes Generados'
        ordering = ['-fecha_generacion']

    def __str__(self):
        return f"{self.titulo} ({self.get_tipo_reporte_display()}) - {self.fecha_generacion.strftime('%d/%m/%Y %H:%M')}"
