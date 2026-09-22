from django.contrib import admin
from .models import Comprobante


@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = (
        'tipo_comprobante',
        'serie',
        'numero_formateado',
        'ruc_emisor',
        'fecha_emision',
        'monto',
        'estado',
        'usuario_registro',
        'fecha_registro',
    )
    list_filter = ('tipo_comprobante', 'estado', 'fecha_emision')
    search_fields = ('ruc_emisor', 'serie', 'numero', 'denominacion_receptor', 'numero_documento_receptor')
    date_hierarchy = 'fecha_emision'
    readonly_fields = ('fecha_registro',)
