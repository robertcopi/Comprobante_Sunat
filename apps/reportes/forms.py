from django import forms
from django.contrib.auth import get_user_model
from apps.comprobantes.models import Comprobante

User = get_user_model()


class ReporteFiltroForm(forms.Form):
    """
    Formulario de filtrado para el módulo de Reportes de Comprobantes.
    Permite filtrar por los 7 criterios oficiales:
    1. Fecha inicio
    2. Fecha fin
    3. RUC
    4. Estado
    5. Tipo de comprobante
    6. Serie
    7. Usuario
    """
    fecha_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}),
        label='Fecha Inicio'
    )
    fecha_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'}),
        label='Fecha Fin'
    )
    ruc = forms.CharField(
        required=False,
        max_length=11,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Ej. 20123456789',
            'maxlength': '11'
        }),
        label='RUC Emisor'
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', '-- Todos los estados --')] + list(Comprobante.EstadoComprobante.choices),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='Estado'
    )
    tipo_comprobante = forms.ChoiceField(
        required=False,
        choices=[('', '-- Todos los tipos --')] + list(Comprobante.TipoComprobante.choices),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='Tipo de Comprobante'
    )
    serie = forms.CharField(
        required=False,
        max_length=4,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm text-uppercase',
            'placeholder': 'Ej. B001, F001',
            'maxlength': '4'
        }),
        label='Serie'
    )
    usuario = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        required=False,
        empty_label='-- Todos los usuarios --',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='Usuario'
    )
