import os
from django import forms
from django.core.exceptions import ValidationError
from .models import LoteImportacion


class ImportacionForm(forms.ModelForm):
    """
    Formulario para carga masiva de archivos Excel y CSV.
    """
    class Meta:
        model = LoteImportacion
        fields = ['archivo']
        widgets = {
            'archivo': forms.FileInput(attrs={
                'class': 'form-control form-control-lg',
                'accept': '.xlsx, .xls, .csv',
            })
        }

    def clean_archivo(self):
        archivo = self.cleaned_data.get('archivo')
        if not archivo:
            raise ValidationError('Debe seleccionar un archivo para importar.')

        nombre = archivo.name.lower()
        extension = os.path.splitext(nombre)[1]

        if extension not in ('.xlsx', '.xls', '.csv'):
            raise ValidationError('Extensión no permitida. Solo se admiten archivos Excel (.xlsx, .xls) y CSV (.csv).')

        # Límite de 15 MB
        if archivo.size > 15 * 1024 * 1024:
            raise ValidationError('El tamaño del archivo no puede exceder los 15 MB.')

        return archivo
