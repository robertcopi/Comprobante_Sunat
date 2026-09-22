from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView,
)

from apps.accounts.decorators import role_required
from apps.accounts.views import get_client_ip
from apps.auditoria.models import RegistroAuditoria
from .models import Comprobante
from .forms import ComprobanteForm, ComprobanteFilterForm


class ComprobanteListView(LoginRequiredMixin, ListView):
    """
    Listado principal de comprobantes con búsqueda avanzada, filtros múltiples y paginación.
    Accesible para todos los usuarios autenticados (Administrador, Supervisor, Trabajador).
    """
    model = Comprobante
    template_name = 'comprobantes/comprobante_list.html'
    context_object_name = 'comprobantes'
    paginate_by = 10

    def get_queryset(self):
        queryset = Comprobante.objects.select_related('usuario_registro').order_by('-fecha_emision', '-id')
        form = ComprobanteFilterForm(self.request.GET)
        
        if form.is_valid():
            q = form.cleaned_data.get('q')
            estado = form.cleaned_data.get('estado')
            tipo = form.cleaned_data.get('tipo_comprobante')
            ruc = form.cleaned_data.get('ruc_emisor')
            serie = form.cleaned_data.get('serie')
            desde = form.cleaned_data.get('fecha_desde')
            hasta = form.cleaned_data.get('fecha_hasta')

            if q:
                q_clean = q.strip()
                # Si el usuario busca número o serie con guión (ej. B001-12)
                numero_filtro = None
                if q_clean.isdigit():
                    numero_filtro = int(q_clean)

                filtro_q = (
                    Q(ruc_emisor__icontains=q_clean) |
                    Q(serie__icontains=q_clean) |
                    Q(denominacion_receptor__icontains=q_clean) |
                    Q(numero_documento_receptor__icontains=q_clean)
                )
                if numero_filtro is not None:
                    filtro_q |= Q(numero=numero_filtro)
                queryset = queryset.filter(filtro_q)

            if estado:
                queryset = queryset.filter(estado=estado)
            if tipo:
                queryset = queryset.filter(tipo_comprobante=tipo)
            if ruc:
                queryset = queryset.filter(ruc_emisor__icontains=ruc.strip())
            if serie:
                queryset = queryset.filter(serie__iexact=serie.strip())
            if desde:
                queryset = queryset.filter(fecha_emision__gte=desde)
            if hasta:
                queryset = queryset.filter(fecha_emision__lte=hasta)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = ComprobanteFilterForm(self.request.GET)
        
        # Preservar parámetros de filtro en la paginación
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['query_params'] = params.urlencode()

        # Resumen de cantidades
        context['total_filtrados'] = self.get_queryset().count()
        context['total_pendientes_sistema'] = Comprobante.objects.filter(
            estado__in=[Comprobante.EstadoComprobante.PENDIENTE, Comprobante.EstadoComprobante.ERROR_CONSULTA]
        ).count()

        # Resumen de procesamiento masivo reciente si existe en la sesión
        context['resumen_masivo'] = self.request.session.pop('resumen_validacion_masiva', None)
        return context


class ComprobanteCreateView(LoginRequiredMixin, CreateView):
    """
    Registro manual de un nuevo comprobante.
    Permiso: Rol ADMINISTRADOR o TRABAJADOR.
    El estado inicial se asigna estrictamente en PENDIENTE.
    """
    model = Comprobante
    form_class = ComprobanteForm
    template_name = 'comprobantes/comprobante_form.html'

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ['ADMINISTRADOR', 'TRABAJADOR']):
            messages.error(request, "Acceso restringido: El rol Supervisor solo tiene permisos de consulta.")
            return redirect('comprobante_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        comprobante = form.save(commit=False)
        comprobante.estado = Comprobante.EstadoComprobante.PENDIENTE
        comprobante.usuario_registro = self.request.user
        comprobante.save()

        # Registro en bitácora de auditoría (PASO 12: REGISTRAR_COMPROBANTE)
        from apps.auditoria.services import AuditoriaService
        AuditoriaService.registrar(
            usuario=self.request.user,
            accion='REGISTRAR_COMPROBANTE',
            objeto_afectado=f"Comprobante {comprobante.codigo_completo}",
            id_objeto=str(comprobante.id),
            descripcion=(
                f"Registrado comprobante {comprobante.get_tipo_comprobante_display()} "
                f"RUC: {comprobante.ruc_emisor}, Monto: S/ {comprobante.monto}"
            ),
            resultado='EXITOSO',
            request=self.request
        )

        messages.success(
            self.request,
            f"Comprobante {comprobante.codigo_completo} registrado exitosamente con estado PENDIENTE."
        )
        return redirect('comprobante_detail', pk=comprobante.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_accion'] = 'Registrar Nuevo Comprobante'
        context['boton_texto'] = 'Guardar Comprobante'
        return context


class ComprobanteDetailView(LoginRequiredMixin, DetailView):
    """
    Vista de detalle del comprobante, incluyendo su historial de validaciones SUNAT (1 a N).
    """
    model = Comprobante
    template_name = 'comprobantes/comprobante_detail.html'
    context_object_name = 'comprobante'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Cargar historial de validaciones con el usuario ejecutor
        context['historial_validaciones'] = self.object.validaciones.select_related('usuario').order_by('-fecha_validacion')
        return context


class ComprobanteUpdateView(LoginRequiredMixin, UpdateView):
    """
    Edición de los datos de un comprobante existente.
    Permiso: Rol ADMINISTRADOR o TRABAJADOR.
    """
    model = Comprobante
    form_class = ComprobanteForm
    template_name = 'comprobantes/comprobante_form.html'

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ['ADMINISTRADOR', 'TRABAJADOR']):
            messages.error(request, "Acceso restringido: No cuenta con permisos para modificar comprobantes.")
            return redirect('comprobante_list')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        comprobante = form.save()

        # Registro en bitácora de auditoría (PASO 12: EDITAR_COMPROBANTE)
        from apps.auditoria.services import AuditoriaService
        AuditoriaService.registrar(
            usuario=self.request.user,
            accion='EDITAR_COMPROBANTE',
            objeto_afectado=f"Comprobante {comprobante.codigo_completo}",
            id_objeto=str(comprobante.id),
            descripcion=f"Datos del comprobante actualizados por el usuario {self.request.user.username}.",
            resultado='EXITOSO',
            request=self.request
        )

        messages.success(self.request, f"Comprobante {comprobante.codigo_completo} actualizado correctamente.")
        return redirect('comprobante_detail', pk=comprobante.pk)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['titulo_accion'] = f"Editar Comprobante {self.object.codigo_completo}"
        context['boton_texto'] = 'Guardar Cambios'
        return context


class ComprobanteDeleteView(LoginRequiredMixin, DeleteView):
    """
    Eliminación de un comprobante.
    Permiso: Rol ADMINISTRADOR (o TRABAJADOR únicamente si el estado es PENDIENTE).
    """
    model = Comprobante
    template_name = 'comprobantes/comprobante_confirm_delete.html'
    context_object_name = 'comprobante'
    success_url = reverse_lazy('comprobante_list')

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        comprobante = self.get_object()

        if user.is_superuser or user.role == 'ADMINISTRADOR':
            return super().dispatch(request, *args, **kwargs)
        
        if user.role == 'TRABAJADOR' and comprobante.estado == Comprobante.EstadoComprobante.PENDIENTE:
            return super().dispatch(request, *args, **kwargs)

        messages.error(request, "No tiene permisos para eliminar este comprobante (solo administradores o comprobantes pendientes).")
        return redirect('comprobante_detail', pk=comprobante.pk)

    def form_valid(self, form):
        comprobante = self.get_object()
        codigo = comprobante.codigo_completo
        cp_id = str(comprobante.id)

        # Registro en auditoría
        from apps.auditoria.services import AuditoriaService
        AuditoriaService.registrar(
            usuario=self.request.user,
            accion='ELIMINAR_COMPROBANTE',
            objeto_afectado=f"Comprobante {codigo}",
            id_objeto=cp_id,
            descripcion="Comprobante eliminado del sistema.",
            resultado='EXITOSO',
            request=self.request
        )

        messages.warning(self.request, f"Comprobante {codigo} ha sido eliminado del sistema.")
        return super().form_valid(form)
