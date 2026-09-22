from django.conf import settings
from django.db import models


class LoteImportacion(models.Model):
    """
    Modelo para gestionar lotes de importación masiva desde archivos Excel (.xlsx) o CSV (.csv).
    """
    class EstadoLote(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PROCESANDO = 'PROCESANDO', 'Procesando'
        COMPLETADO = 'COMPLETADO', 'Completado'
        ERROR = 'ERROR', 'Error en la Carga'

    nombre_archivo = models.CharField(
        max_length=255,
        verbose_name='Nombre del Archivo'
    )
    archivo = models.FileField(
        upload_to='importaciones/%Y/%m/',
        verbose_name='Archivo Subido'
    )
    fecha_carga = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Carga'
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lotes_importacion',
        verbose_name='Usuario que Realizó la Carga'
    )
    
    # Métricas requeridas
    total_leidos = models.PositiveIntegerField(
        default=0,
        verbose_name='Total Leído'
    )
    importados_correctos = models.PositiveIntegerField(
        default=0,
        verbose_name='Importados Correctamente'
    )
    total_duplicados = models.PositiveIntegerField(
        default=0,
        verbose_name='Total Duplicados'
    )
    total_errores = models.PositiveIntegerField(
        default=0,
        verbose_name='Total con Errores'
    )
    
    estado = models.CharField(
        max_length=20,
        choices=EstadoLote.choices,
        default=EstadoLote.PENDIENTE,
        verbose_name='Estado'
    )

    # Detalle de incidencias para visualización
    errores_detalle = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Detalle de Errores'
    )
    duplicados_detalle = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Detalle de Duplicados'
    )

    class Meta:
        verbose_name = 'Lote de Importación'
        verbose_name_plural = 'Lotes de Importación'
        ordering = ['-fecha_carga']

    def __str__(self):
        return f"Lote #{self.id} - {self.nombre_archivo} [{self.get_estado_display()}]"
