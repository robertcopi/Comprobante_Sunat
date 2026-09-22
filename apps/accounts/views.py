from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.auditoria.models import RegistroAuditoria
from apps.comprobantes.models import Comprobante
from apps.importaciones.models import LoteImportacion
from apps.validaciones.models import ValidacionSunat
from .forms import LoginForm


def get_client_ip(request):
    """Obtiene la IP pública o local real del cliente."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


class CustomLoginView(LoginView):
    """
    Vista de inicio de sesión con registro de auditoría y redirección segura.
    """
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        user = form.get_user()
        login(self.request, user)

        # Registro en bitácora de auditoría (PASO 12: LOGIN)
        from apps.auditoria.services import AuditoriaService
        AuditoriaService.registrar(
            usuario=user,
            accion='LOGIN',
            objeto_afectado=f"Usuario {user.username}",
            id_objeto=str(user.id),
            descripcion=f"Acceso exitoso al sistema con rol: {user.get_role_display()}",
            resultado='EXITOSO',
            request=self.request
        )

        messages.success(self.request, f"¡Bienvenido(a) {user.get_full_name() or user.username}! Rol: {user.get_role_display()}")
        return redirect('dashboard')

    def form_invalid(self, form):
        # Registro en bitácora de auditoría para intento fallido (sin almacenar contraseña)
        username = form.data.get('username', 'Desconocido')
        from apps.auditoria.services import AuditoriaService
        AuditoriaService.registrar(
            usuario=None,
            accion='LOGIN',
            objeto_afectado=f"Usuario {username}",
            descripcion=f"Intento fallido de inicio de sesión para el usuario '{username}'. Credenciales inválidas.",
            resultado='FALLIDO',
            request=self.request
        )
        return super().form_invalid(form)


class CustomLogoutView(View):
    """
    Vista de cierre de sesión segura con registro de auditoría.
    """
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            try:
                RegistroAuditoria.objects.create(
                    usuario=request.user,
                    accion='Cierre de Sesión',
                    objeto_afectado=f"Usuario {request.user.username}",
                    descripcion="Sesión cerrada correctamente",
                    ip_origen=get_client_ip(request)
                )
            except Exception:
                pass
            logout(request)
            messages.info(request, "Ha cerrado sesión correctamente.")
        return redirect('login')

    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)


class DashboardView(LoginRequiredMixin, TemplateView):
    """
    Panel de control empresarial que adapta métricas y acciones según el rol del usuario.
    Calcula estadísticas en una sola consulta agregada (sin iterar en memoria),
    proporciona datos para gráficos (Chart.js) y permite filtrar por rango de fechas.
    """
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        from datetime import datetime, time, timedelta
        import json
        from django.db.models import Count, Q
        from django.db.models.functions import TruncDate
        from django.utils import timezone
        from django.utils.dateparse import parse_date

        context = super().get_context_data(**kwargs)
        user = self.request.user

        # 1. Filtros por rango de fechas
        fecha_desde_raw = self.request.GET.get('fecha_desde')
        fecha_hasta_raw = self.request.GET.get('fecha_hasta')
        fecha_desde = parse_date(fecha_desde_raw) if fecha_desde_raw else None
        fecha_hasta = parse_date(fecha_hasta_raw) if fecha_hasta_raw else None

        comprobantes_qs = Comprobante.objects.all()
        validaciones_qs = ValidacionSunat.objects.all()

        if fecha_desde:
            dt_desde = timezone.make_aware(datetime.combine(fecha_desde, time.min))
            comprobantes_qs = comprobantes_qs.filter(fecha_emision__gte=fecha_desde)
            validaciones_qs = validaciones_qs.filter(fecha_validacion__gte=dt_desde)

        if fecha_hasta:
            dt_hasta = timezone.make_aware(datetime.combine(fecha_hasta, time.max))
            comprobantes_qs = comprobantes_qs.filter(fecha_emision__lte=fecha_hasta)
            validaciones_qs = validaciones_qs.filter(fecha_validacion__lte=dt_hasta)

        # 2. Consulta agregada ultra-eficiente en una sola consulta SQL (sin iterar en memoria)
        kpis = comprobantes_qs.aggregate(
            total=Count('id'),
            pendientes=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.PENDIENTE)),
            aceptados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.ACEPTADO)),
            observados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.OBSERVADO)),
            rechazados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.RECHAZADO)),
            errores=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.ERROR_CONSULTA)),
        )

        total_comprobantes = kpis['total'] or 0
        pendientes = kpis['pendientes'] or 0
        aceptados = kpis['aceptados'] or 0
        observados = kpis['observados'] or 0
        rechazados = kpis['rechazados'] or 0
        errores = kpis['errores'] or 0

        # 3. Comprobantes procesados hoy (jornada actual)
        hoy = timezone.now().date()
        procesados_hoy = ValidacionSunat.objects.filter(fecha_validacion__date=hoy).count()
        registrados_hoy = Comprobante.objects.filter(fecha_registro__date=hoy).count()

        # 4. Actividad reciente: últimas validaciones y últimas importaciones
        ultimas_validaciones = ValidacionSunat.objects.select_related('comprobante', 'usuario').order_by('-fecha_validacion')[:6]
        ultimas_importaciones = LoteImportacion.objects.select_related('usuario').order_by('-fecha_carga')[:6]
        total_lotes = LoteImportacion.objects.count()

        # 5. Gráfico 1: Comprobantes por estado (Chart.js Dona)
        chart_estados = {
            'labels': ['Aceptados', 'Observados', 'Rechazados', 'Pendientes', 'Error Consulta'],
            'data': [aceptados, observados, rechazados, pendientes, errores],
            'colors': ['#198754', '#ffc107', '#dc3545', '#0dcaf0', '#6c757d']
        }

        # 6. Gráfico 2: Validaciones por fecha (Chart.js Barras/Líneas temporales)
        if not fecha_desde:
            hace_14_dias = timezone.now() - timedelta(days=14)
            val_chart_qs = ValidacionSunat.objects.filter(fecha_validacion__gte=hace_14_dias)
        else:
            val_chart_qs = validaciones_qs

        serie_fechas = (
            val_chart_qs
            .annotate(dia=TruncDate('fecha_validacion'))
            .values('dia')
            .annotate(
                total=Count('id'),
                aceptados=Count('id', filter=Q(estado_sunat__icontains='Aceptado')),
                rechazados=Count('id', filter=Q(estado_sunat__icontains='Rechazado') | Q(codigo_respuesta__in=['0', '2', '4'])),
                errores=Count('id', filter=Q(estado_sunat__icontains='ERROR') | Q(estado_sunat='ERROR_LOCAL'))
            )
            .order_by('dia')
        )

        fechas_labels = []
        datos_totales = []
        datos_aceptados = []
        datos_rechazados = []
        for item in serie_fechas:
            if item['dia']:
                fechas_labels.append(item['dia'].strftime('%d/%m'))
                datos_totales.append(item['total'])
                datos_aceptados.append(item['aceptados'])
                datos_rechazados.append(item['rechazados'])

        chart_fechas = {
            'labels': fechas_labels,
            'totales': datos_totales,
            'aceptados': datos_aceptados,
            'rechazados': datos_rechazados,
        }

        context.update({
            # KPIs requeridos
            'total_comprobantes': total_comprobantes,
            'aceptados': aceptados,
            'observados': observados,
            'rechazados': rechazados,
            'pendientes': pendientes,
            'errores': errores,
            # Indicadores adicionales
            'procesados_hoy': procesados_hoy,
            'registrados_hoy': registrados_hoy,
            # Tablas recientes
            'ultimas_validaciones': ultimas_validaciones,
            'ultimas_importaciones': ultimas_importaciones,
            'total_lotes': total_lotes,
            # Filtros
            'fecha_desde': fecha_desde_raw or '',
            'fecha_hasta': fecha_hasta_raw or '',
            'filtro_activo': bool(fecha_desde_raw or fecha_hasta_raw),
            # Gráficos JSON
            'chart_estados_json': json.dumps(chart_estados),
            'chart_fechas_json': json.dumps(chart_fechas),
            'user_role': user.get_role_display(),
        })
        return context
