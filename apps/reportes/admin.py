from django.contrib import admin
from .models import ReporteGenerado


@admin.register(ReporteGenerado)
class ReporteGeneradoAdmin(admin.ModelAdmin):
    list_display = ('id', 'titulo', 'tipo_reporte', 'usuario', 'fecha_generacion')
    list_filter = ('tipo_reporte', 'fecha_generacion')
    search_fields = ('titulo', 'usuario__username')
    readonly_fields = ('fecha_generacion',)
