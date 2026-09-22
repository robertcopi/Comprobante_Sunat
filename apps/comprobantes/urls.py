from django.urls import path
from .views import (
    ComprobanteListView,
    ComprobanteCreateView,
    ComprobanteDetailView,
    ComprobanteUpdateView,
    ComprobanteDeleteView,
)

from apps.validaciones.views import (
    ValidarComprobanteIndividualView,
    ValidarComprobantesMasivoView,
)

urlpatterns = [
    path('', ComprobanteListView.as_view(), name='comprobante_list'),
    path('nuevo/', ComprobanteCreateView.as_view(), name='comprobante_create'),
    path('<int:pk>/', ComprobanteDetailView.as_view(), name='comprobante_detail'),
    path('<int:pk>/editar/', ComprobanteUpdateView.as_view(), name='comprobante_update'),
    path('<int:pk>/eliminar/', ComprobanteDeleteView.as_view(), name='comprobante_delete'),
    path('<int:pk>/validar/', ValidarComprobanteIndividualView.as_view(), name='comprobante_validar'),
    path('validar-masivo/', ValidarComprobantesMasivoView.as_view(), name='comprobante_validar_masivo'),
]
