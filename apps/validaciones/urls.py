from django.urls import path
from .views import (
    HistorialValidacionesListView,
    ValidarComprobanteIndividualView,
    ValidarComprobantesMasivoView,
)

urlpatterns = [
    path('', HistorialValidacionesListView.as_view(), name='historial_validaciones'),
    path('historial/', HistorialValidacionesListView.as_view(), name='historial_validaciones_alias'),
    path('comprobante/<int:pk>/', ValidarComprobanteIndividualView.as_view(), name='validar_comprobante_individual'),
    path('masivo/', ValidarComprobantesMasivoView.as_view(), name='validar_comprobantes_masivo'),
]
