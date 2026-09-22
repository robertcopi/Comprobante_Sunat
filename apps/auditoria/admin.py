from django.contrib import admin
from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'usuario', 'accion', 'objeto_afectado', 'id_objeto', 'resultado', 'ip_origen')
    list_filter = ('accion', 'resultado', 'fecha')
    search_fields = ('descripcion', 'objeto_afectado', 'id_objeto', 'usuario__username', 'ip_origen')
    readonly_fields = ('fecha',)
