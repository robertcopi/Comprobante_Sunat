from django.contrib import admin
from django.shortcuts import redirect
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('comprobantes/', include('apps.comprobantes.urls')),
    path('importaciones/', include('apps.importaciones.urls')),
    path('validaciones/', include('apps.validaciones.urls')),
    path('auditoria/', include('apps.auditoria.urls')),
    path('', lambda request: redirect('dashboard'), name='root'),
]
