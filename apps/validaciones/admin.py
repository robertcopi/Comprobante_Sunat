from django.contrib import admin
from .models import ValidacionSunat


@admin.register(ValidacionSunat)
class ValidacionSunatAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'comprobante',
        'estado_sunat',
        'codigo_respuesta',
        'usuario',
        'fecha_validacion',
    )
    list_filter = ('estado_sunat', 'fecha_validacion')
    search_fields = (
        'comprobante__serie',
        'comprobante__numero',
        'comprobante__ruc_emisor',
        'codigo_respuesta',
        'mensaje',
    )
    readonly_fields = ('fecha_validacion',)
