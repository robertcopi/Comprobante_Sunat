from django.contrib import admin
from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'accion', 'objeto_afectado', 'ip_origen')
    list_filter = ('accion', 'fecha')
    search_fields = ('descripcion', 'objeto_afectado', 'usuario__username', 'ip_origen')
    readonly_fields = ('fecha',)
