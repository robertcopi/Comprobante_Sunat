from django.contrib import admin
from .models import LoteImportacion


@admin.register(LoteImportacion)
class LoteImportacionAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'nombre_archivo',
        'usuario',
        'total_leidos',
        'importados_correctos',
        'total_duplicados',
        'total_errores',
        'estado',
        'fecha_carga',
    )
    list_filter = ('estado', 'fecha_carga')
    search_fields = ('nombre_archivo', 'usuario__username')
    readonly_fields = ('fecha_carga',)
