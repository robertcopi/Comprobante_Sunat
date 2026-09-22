from django.urls import path
from .views import (
    ReporteComprobantesView,
    ReporteExportarExcelView,
    ReporteExportarPdfView,
)

urlpatterns = [
    path('', ReporteComprobantesView.as_view(), name='reporte_comprobantes'),
    path('exportar/excel/', ReporteExportarExcelView.as_view(), name='reporte_exportar_excel'),
    path('exportar/pdf/', ReporteExportarPdfView.as_view(), name='reporte_exportar_pdf'),
]
