from django.urls import path
from .views import (
    ImportacionListView,
    ImportacionUploadView,
    ImportacionDetailView,
    DescargarPlantillaExcelView,
    DescargarPlantillaCsvView,
)

urlpatterns = [
    path('', ImportacionListView.as_view(), name='importacion_list'),
    path('nueva/', ImportacionUploadView.as_view(), name='importacion_upload'),
    path('<int:pk>/', ImportacionDetailView.as_view(), name='importacion_detail'),
    path('plantilla/excel/', DescargarPlantillaExcelView.as_view(), name='importacion_plantilla_excel'),
    path('plantilla/csv/', DescargarPlantillaCsvView.as_view(), name='importacion_plantilla_csv'),
]
