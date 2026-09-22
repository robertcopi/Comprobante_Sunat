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
    """
    template_name = 'dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # Métricas generales de comprobantes
        total_comprobantes = Comprobante.objects.count()
        pendientes = Comprobante.objects.filter(estado=Comprobante.EstadoComprobante.PENDIENTE).count()
        aceptados = Comprobante.objects.filter(estado=Comprobante.EstadoComprobante.ACEPTADO).count()
        observados = Comprobante.objects.filter(estado=Comprobante.EstadoComprobante.OBSERVADO).count()
        rechazados = Comprobante.objects.filter(estado=Comprobante.EstadoComprobante.RECHAZADO).count()
        errores = Comprobante.objects.filter(estado=Comprobante.EstadoComprobante.ERROR_CONSULTA).count()

        # Últimos registros
        ultimos_comprobantes = Comprobante.objects.select_related('usuario_registro')[:5]
        ultimas_validaciones = ValidacionSunat.objects.select_related('comprobante', 'usuario')[:5]

        # Métricas de importación para Trabajador / Administrador
        total_lotes = LoteImportacion.objects.count()

        context.update({
            'total_comprobantes': total_comprobantes,
            'pendientes': pendientes,
            'aceptados': aceptados,
            'observados': observados,
            'rechazados': rechazados,
            'errores': errores,
            'ultimos_comprobantes': ultimos_comprobantes,
            'ultimas_validaciones': ultimas_validaciones,
            'total_lotes': total_lotes,
            'user_role': user.get_role_display(),
        })
        return context
