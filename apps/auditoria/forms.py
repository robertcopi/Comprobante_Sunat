from django import forms
from django.contrib.auth import get_user_model
from .models import RegistroAuditoria

User = get_user_model()


class AuditoriaFiltroForm(forms.Form):
    """
    Formulario de filtrado para la bitácora de auditoría.
    Permite filtrar por Usuario, Acción y Rango de Fechas.
    """
    usuario = forms.ModelChoiceField(
        queryset=User.objects.all().order_by('username'),
        required=False,
        empty_label='-- Todos los usuarios --',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    accion = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'})
    )

    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control form-control-sm'})
    )

    resultado = forms.ChoiceField(
        required=False,
        choices=[('', '-- Todos los resultados --')] + list(RegistroAuditoria.ResultadoAuditoria.choices),
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Buscar por objeto, ID o detalle...'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Poblar acciones dinámicamente incluyendo las 7 acciones principales
        acciones_choices = [('', '-- Todas las acciones --')] + list(RegistroAuditoria.AccionAuditoria.choices)
        self.fields['accion'].choices = acciones_choices
