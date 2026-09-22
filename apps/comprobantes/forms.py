import re
from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from .models import Comprobante


class ComprobanteForm(forms.ModelForm):
    """
    Formulario para creación y edición de comprobantes electrónicos con validaciones SUNAT.
    """
    class Meta:
        model = Comprobante
        fields = [
            'ruc_emisor',
            'tipo_comprobante',
            'serie',
            'numero',
            'fecha_emision',
            'monto',
            'tipo_documento_receptor',
            'numero_documento_receptor',
            'denominacion_receptor',
        ]
        widgets = {
            'ruc_emisor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 20123456789',
                'maxlength': '11',
                'pattern': r'\d{11}',
                'autocomplete': 'off',
            }),
            'tipo_comprobante': forms.Select(attrs={
                'class': 'form-select',
            }),
            'serie': forms.TextInput(attrs={
                'class': 'form-control text-uppercase',
                'placeholder': 'Ej. B001, F001, EB01',
                'maxlength': '4',
                'style': 'text-transform: uppercase;',
            }),
            'numero': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej. 1250',
                'min': '1',
                'max': '99999999',
            }),
            'fecha_emision': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0.00',
                'step': '0.01',
                'min': '0.01',
            }),
            'tipo_documento_receptor': forms.Select(
                choices=[
                    ('', '-- Seleccione Tipo (Opcional) --'),
                    ('1', '1 - DNI'),
                    ('6', '6 - RUC'),
                    ('4', '4 - Carnet de Extranjería'),
                    ('7', '7 - Pasaporte'),
                    ('0', '0 - Sin Documento / Varios'),
                ],
                attrs={'class': 'form-select'}
            ),
            'numero_documento_receptor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'N° de DNI / RUC del cliente',
                'maxlength': '15',
            }),
            'denominacion_receptor': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombres y Apellidos o Razón Social',
                'maxlength': '255',
            }),
        }

    def clean_ruc_emisor(self):
        ruc = self.cleaned_data.get('ruc_emisor', '').strip()
        if not re.match(r'^\d{11}$', ruc):
            raise ValidationError('El RUC del emisor debe tener exactamente 11 dígitos numéricos.')
        if not (ruc.startswith('10') or ruc.startswith('20') or ruc.startswith('15') or ruc.startswith('17')):
            raise ValidationError('El RUC debe iniciar con un prefijo válido en Perú (10, 20, 15, 17).')
        return ruc

    def clean_serie(self):
        serie = self.cleaned_data.get('serie', '').strip().upper()
        if not re.match(r'^[B|F|E][A-Z0-9]{3}$', serie):
            raise ValidationError('La serie debe iniciar con B, F o E y tener 4 caracteres alfanuméricos (ej. B001, F001, EB01).')
        return serie

    def clean_numero(self):
        numero = self.cleaned_data.get('numero')
        if numero is None or numero <= 0:
            raise ValidationError('El número correlativo debe ser un entero positivo mayor a cero.')
        if numero > 99999999:
            raise ValidationError('El número correlativo no puede exceder los 8 dígitos (99999999).')
        return numero

    def clean_fecha_emision(self):
        fecha = self.cleaned_data.get('fecha_emision')
        if fecha and fecha > date.today():
            raise ValidationError('La fecha de emisión no puede ser posterior a la fecha actual.')
        return fecha

    def clean_monto(self):
        monto = self.cleaned_data.get('monto')
        if monto is None or monto <= 0:
            raise ValidationError('El importe del comprobante debe ser un monto mayor a cero.')
        return monto

    def clean(self):
        cleaned_data = super().clean()
        ruc_emisor = cleaned_data.get('ruc_emisor')
        tipo_comprobante = cleaned_data.get('tipo_comprobante')
        serie = cleaned_data.get('serie')
        numero = cleaned_data.get('numero')

        if ruc_emisor and tipo_comprobante and serie and numero:
            # Validar unicidad (RUC + Tipo + Serie + Número)
            qs = Comprobante.objects.filter(
                ruc_emisor=ruc_emisor,
                tipo_comprobante=tipo_comprobante,
                serie=serie,
                numero=numero
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.exists():
                raise ValidationError(
                    f'Ya existe un comprobante registrado con este RUC ({ruc_emisor}), '
                    f'tipo ({tipo_comprobante}), serie ({serie}) y número ({str(numero).zfill(8)}).'
                )

        return cleaned_data


class ComprobanteFilterForm(forms.Form):
    """
    Formulario para búsqueda y filtros avanzados en el listado de comprobantes.
    """
    q = forms.CharField(
        required=False,
        label='Búsqueda General',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por RUC, serie, número o cliente...',
        })
    )
    estado = forms.ChoiceField(
        required=False,
        choices=[('', '-- Todos los Estados --')] + Comprobante.EstadoComprobante.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    tipo_comprobante = forms.ChoiceField(
        required=False,
        choices=[('', '-- Todos los Tipos --')] + Comprobante.TipoComprobante.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    ruc_emisor = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Filtrar por RUC',
            'maxlength': '11',
        })
    )
    serie = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control text-uppercase',
            'placeholder': 'Serie (ej. B001)',
            'maxlength': '4',
        })
    )
    fecha_desde = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        })
    )
    fecha_hasta = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        })
    )
