from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Comprobante(models.Model):
    """
    Modelo de Comprobante Electrónico (Boleta, Factura, etc.)
    Garantiza unicidad fiscal mediante: RUC emisor + tipo + serie + número.
    """
    class TipoComprobante(models.TextChoices):
        BOLETA = '03', '03 - Boleta de Venta Electrónica'
        FACTURA = '01', '01 - Factura Electrónica'
        NOTA_CREDITO = '07', '07 - Nota de Crédito'
        NOTA_DEBITO = '08', '08 - Nota de Débito'

    class EstadoComprobante(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        ACEPTADO = 'ACEPTADO', 'Aceptado'
        OBSERVADO = 'OBSERVADO', 'Observado'
        RECHAZADO = 'RECHAZADO', 'Rechazado'
        ERROR_CONSULTA = 'ERROR_CONSULTA', 'Error de Consulta'

    # Datos tributarios requeridos
    ruc_emisor = models.CharField(
        max_length=11,
        validators=[RegexValidator(r'^\d{11}$', 'El RUC debe tener 11 dígitos numéricos.')],
        verbose_name='RUC Emisor'
    )
    tipo_comprobante = models.CharField(
        max_length=2,
        choices=TipoComprobante.choices,
        default=TipoComprobante.BOLETA,
        verbose_name='Tipo de Comprobante'
    )
    serie = models.CharField(
        max_length=4,
        validators=[RegexValidator(r'^[B|F|E][A-Z0-9]{3}$', 'Serie alfanumérica de 4 caracteres (ej. B001, F001, EB01).')],
        verbose_name='Serie'
    )
    numero = models.PositiveIntegerField(
        verbose_name='Número Correlativo'
    )
    fecha_emision = models.DateField(
        verbose_name='Fecha de Emisión'
    )
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Monto Total'
    )
    estado = models.CharField(
        max_length=20,
        choices=EstadoComprobante.choices,
        default=EstadoComprobante.PENDIENTE,
        verbose_name='Estado'
    )

    # Datos complementarios del cliente/receptor
    tipo_documento_receptor = models.CharField(
        max_length=2,
        blank=True,
        null=True,
        verbose_name='Tipo Doc. Receptor'
    )
    numero_documento_receptor = models.CharField(
        max_length=15,
        blank=True,
        null=True,
        verbose_name='Número Doc. Receptor'
    )
    denominacion_receptor = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Razón Social / Nombre Receptor'
    )

    # Trazabilidad
    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de Registro'
    )
    usuario_registro = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='comprobantes_registrados',
        verbose_name='Usuario que Registró'
    )

    class Meta:
        verbose_name = 'Comprobante'
        verbose_name_plural = 'Comprobantes'
        ordering = ['-fecha_emision', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['ruc_emisor', 'tipo_comprobante', 'serie', 'numero'],
                name='unique_comprobante_ruc_tipo_serie_numero'
            )
        ]
        indexes = [
            models.Index(fields=['ruc_emisor', 'tipo_comprobante', 'serie', 'numero']),
            models.Index(fields=['estado']),
            models.Index(fields=['fecha_emision']),
        ]

    def __str__(self):
        return f"{self.get_tipo_comprobante_display()} {self.serie}-{str(self.numero).zfill(8)} (RUC: {self.ruc_emisor})"

    @property
    def numero_formateado(self):
        return str(self.numero).zfill(8)

    @property
    def codigo_completo(self):
        return f"{self.serie}-{self.numero_formateado}"
