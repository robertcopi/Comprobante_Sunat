import csv
from datetime import datetime, time
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views import View
from django.views.generic import ListView

from .forms import AuditoriaFiltroForm
from .models import RegistroAuditoria
from .services import AuditoriaService


class AuthorizedAuditoriaMixin(UserPassesTestMixin):
    """
    Mixin de seguridad que restringe el acceso exclusivamente a usuarios autorizados.
    Solo usuarios con rol ADMINISTRADOR o superusuarios pueden consultar la auditoría.
    """
    raise_exception = False

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        return bool(user.is_superuser or getattr(user, 'puede_ver_auditoria', False) or getattr(user, 'is_administrador', False))

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect('login')
        messages.error(
            self.request,
            "Acceso restringido: Únicamente los usuarios administradores autorizados tienen acceso a la bitácora de auditoría."
        )
        return redirect('dashboard')


class AuditoriaListView(LoginRequiredMixin, AuthorizedAuditoriaMixin, ListView):
    """
    Vista de consulta y supervisión de la bitácora de auditoría para usuarios autorizados.
    Incluye filtros por Usuario, Acción, Rango de Fechas, Resultado y paginación.
    """
    model = RegistroAuditoria
    template_name = 'auditoria/auditoria_list.html'
    context_object_name = 'registros'
    paginate_by = 20

    def get_queryset(self):
        qs = RegistroAuditoria.objects.select_related('usuario').all()
        form = AuditoriaFiltroForm(self.request.GET)

        if form.is_valid():
            usuario = form.cleaned_data.get('usuario')
            accion = form.cleaned_data.get('accion')
            fecha_desde = form.cleaned_data.get('fecha_desde')
            fecha_hasta = form.cleaned_data.get('fecha_hasta')
            resultado = form.cleaned_data.get('resultado')
            q = form.cleaned_data.get('q')

            if usuario:
                qs = qs.filter(usuario=usuario)

            if accion:
                qs = qs.filter(accion=accion)

            if fecha_desde:
                dt_desde = timezone.make_aware(datetime.combine(fecha_desde, time.min))
                qs = qs.filter(fecha__gte=dt_desde)

            if fecha_hasta:
                dt_hasta = timezone.make_aware(datetime.combine(fecha_hasta, time.max))
                qs = qs.filter(fecha__lte=dt_hasta)

            if resultado:
                qs = qs.filter(resultado=resultado)

            if q:
                qs = qs.filter(
                    Q(objeto_afectado__icontains=q) |
                    Q(id_objeto__icontains=q) |
                    Q(descripcion__icontains=q)
                )

        return qs.order_by('-fecha')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = AuditoriaFiltroForm(self.request.GET)
        context['form'] = form

        # Preservar parámetros en la paginación
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['url_params'] = params.urlencode()

        # Métricas contextuales
        total_logs = RegistroAuditoria.objects.count()
        context['total_registros'] = total_logs
        context['total_filtrados'] = self.get_queryset().count()
        context['total_logins'] = RegistroAuditoria.objects.filter(accion='LOGIN').count()
        context['total_validaciones'] = RegistroAuditoria.objects.filter(
            accion__in=['VALIDAR_COMPROBANTE', 'VALIDACION_MASIVA']
        ).count()
        context['total_errores'] = RegistroAuditoria.objects.filter(
            resultado__in=['ERROR', 'FALLIDO']
        ).count()

        return context


class AuditoriaExportarCsvView(LoginRequiredMixin, AuthorizedAuditoriaMixin, View):
    """
    Exportación de registros filtrados de auditoría a archivo CSV.
    Registra la acción oficial: EXPORTAR_REPORTE.
    """
    def get(self, request, *args, **kwargs):
        view = AuditoriaListView()
        view.request = request
        qs = view.get_queryset()

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        response['Content-Disposition'] = f'attachment; filename="auditoria_sistema_{timestamp}.csv"'

        # BOM para compatibilidad con Microsoft Excel
        response.write('\ufeff'.encode('utf-8'))
        writer = csv.writer(response)

        # Encabezados
        writer.writerow([
            'ID',
            'Fecha y Hora',
            'Usuario',
            'Acción',
            'Objeto Afectado',
            'ID del Objeto',
            'Resultado',
            'Descripción',
            'IP Origen'
        ])

        total_filas = 0
        for reg in qs[:2000]:  # Limite de seguridad
            total_filas += 1
            writer.writerow([
                reg.id,
                reg.fecha.strftime('%d/%m/%Y %H:%M:%S'),
                reg.usuario.username if reg.usuario else 'Sistema',
                reg.accion,
                reg.objeto_afectado,
                reg.id_objeto or '',
                reg.resultado,
                reg.descripcion,
                reg.ip_origen or ''
            ])

        # Registrar la acción de auditoría requerida (PASO 12: EXPORTAR_REPORTE)
        AuditoriaService.registrar(
            usuario=request.user,
            accion='EXPORTAR_REPORTE',
            objeto_afectado='Bitácora de Auditoría (CSV)',
            id_objeto='export_auditoria_csv',
            descripcion=f"Exportación de {total_filas} registros de auditoría a formato CSV.",
            resultado='EXITOSO',
            request=request
        )

        return response
