from django.urls import path
from .views import AuditoriaListView, AuditoriaExportarCsvView

urlpatterns = [
    path('', AuditoriaListView.as_view(), name='auditoria_list'),
    path('exportar/', AuditoriaExportarCsvView.as_view(), name='auditoria_exportar_csv'),
]
