"""
Formularios para filtros y búsquedas en el módulo de validaciones.
"""

from django import forms
from django.contrib.auth import get_user_model

User = get_user_model()


class ValidacionFilterForm(forms.Form):
    """
    Formulario de filtros avanzados para el historial de validaciones SUNAT.
    Filtros requeridos:
    - Fecha (rango desde / hasta)
    - Estado (Aceptado, Observado, Rechazado, Error de Consulta, Pendiente)
    - Usuario (consultante)
    - RUC (emisor del comprobante)
    - Serie (del comprobante)
    """
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Desde'
        })
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control',
            'placeholder': 'Hasta'
        })
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[
            ('', 'Todos los estados'),
            ('ACEPTADO', 'Aceptado'),
            ('OBSERVADO', 'Observado'),
            ('RECHAZADO', 'Rechazado'),
            ('ERROR_CONSULTA', 'Error de Consulta'),
            ('PENDIENTE', 'Pendiente'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    usuario = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        required=False,
        empty_label='Todos los usuarios',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    ruc = forms.CharField(
        required=False,
        max_length=11,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'RUC emisor (11 dígitos)'
        })
    )
    serie = forms.CharField(
        required=False,
        max_length=4,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Serie (ej. F001)'
        })
    )
