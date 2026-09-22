from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def role_required(allowed_roles):
    """
    Decorador que restringe el acceso a una vista a usuarios autenticados
    con roles especificados en `allowed_roles`.
    Los superusuarios siempre tienen acceso total.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in allowed_roles:
                return view_func(request, *args, **kwargs)
            
            messages.error(
                request,
                f"Acceso denegado: Su rol ({user.get_role_display()}) no cuenta con permisos para este recurso."
            )
            return redirect('dashboard')
        return _wrapped_view
    return decorator


def admin_required(view_func):
    """Acceso exclusivo para rol ADMINISTRADOR o superusuarios."""
    return role_required(['ADMINISTRADOR'])(view_func)


def supervisor_required(view_func):
    """Acceso para ADMINISTRADOR y SUPERVISOR."""
    return role_required(['ADMINISTRADOR', 'SUPERVISOR'])(view_func)


def trabajador_required(view_func):
    """Acceso para ADMINISTRADOR y TRABAJADOR."""
    return role_required(['ADMINISTRADOR', 'TRABAJADOR'])(view_func)
