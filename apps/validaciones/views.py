"""
Vistas para la validación de comprobantes ante SUNAT.
"""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from apps.accounts.views import get_client_ip
from apps.comprobantes.models import Comprobante
from apps.validaciones.forms import ValidacionFilterForm
from apps.validaciones.models import ValidacionSunat
from apps.validaciones.services import ValidacionComprobanteService, ValidacionMasivaService


class ValidarComprobanteIndividualView(LoginRequiredMixin, View):
    """
    Vista para ejecutar la validación individual de un comprobante ante SUNAT.
    Método POST: ejecuta el flujo de los 9 pasos y redirecciona al detalle con mensajes Bootstrap.
    """

    def post(self, request, pk, *args, **kwargs):
        # Control de acceso por rol: Trabajador, Administrador o Superusuario
        user = request.user
        if not (user.is_superuser or user.role in ['ADMINISTRADOR', 'TRABAJADOR']):
            messages.error(request, "Acceso restringido: El rol Supervisor solo tiene permisos de consulta.")
            return redirect('comprobante_detail', pk=pk)

        comprobante = get_object_or_404(Comprobante, pk=pk)
        ip = get_client_ip(request)

        service = ValidacionComprobanteService(ip_origen=ip)
        resultado = service.ejecutar_validacion(comprobante_id=comprobante.pk, usuario=user)

        # Notificación visual enriquecida con Bootstrap
        if resultado.exito:
            if resultado.estado_comprobante == Comprobante.EstadoComprobante.ACEPTADO:
                messages.success(
                    request,
                    f"¡Comprobante {comprobante.codigo_completo} VALIDADO y ACEPTADO por SUNAT! "
                    f"Estado: {resultado.estado_sunat_desc}. (Cód: {resultado.codigo_respuesta})"
                )
            elif resultado.estado_comprobante == Comprobante.EstadoComprobante.OBSERVADO:
                messages.warning(
                    request,
                    f"Comprobante {comprobante.codigo_completo} OBSERVADO por SUNAT: {resultado.mensaje}"
                )
            elif resultado.estado_comprobante == Comprobante.EstadoComprobante.RECHAZADO:
                messages.error(
                    request,
                    f"Comprobante {comprobante.codigo_completo} RECHAZADO por SUNAT. Estado: {resultado.estado_sunat_desc}."
                )
            else:
                messages.info(request, f"Resultado SUNAT: {resultado.mensaje}")
        else:
            # Errores técnicos, de timeout o formato (no implican rechazo)
            messages.error(
                request,
                f"No se pudo completar la validación con SUNAT [{resultado.codigo_respuesta}]: {resultado.mensaje} "
                f"El estado del comprobante se estableció en ERROR_CONSULTA."
            )

        return redirect('comprobante_detail', pk=pk)

    def get(self, request, pk, *args, **kwargs):
        """Si se accede vía GET, redireccionar al detalle para evitar llamadas accidentales."""
        return redirect('comprobante_detail', pk=pk)


class ValidarComprobantesMasivoView(LoginRequiredMixin, View):
    """
    Vista para ejecutar la validación masiva por lotes de comprobantes ante SUNAT.
    Soporta:
    1. Selección manual de IDs mediante checkboxes.
    2. Validación de todos los pendientes (flag validar_todos_pendientes=1).
    Procesamiento secuencial controlado respetando restricciones de SUNAT.
    """

    def post(self, request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.role in ['ADMINISTRADOR', 'TRABAJADOR']):
            messages.error(request, "Acceso restringido: El rol Supervisor solo tiene permisos de consulta.")
            return redirect('comprobante_list')

        validar_todos = request.POST.get('validar_todos_pendientes') in ['1', 'true', 'True']
        comprobantes_ids_raw = request.POST.getlist('comprobantes_ids')
        revalidar_aceptados = request.POST.get('revalidar_aceptados') in ['1', 'true', 'True']

        # Parsear IDs numéricos válidos
        comprobantes_ids = []
        for item in comprobantes_ids_raw:
            if str(item).isdigit():
                comprobantes_ids.append(int(item))

        if not validar_todos and not comprobantes_ids:
            messages.warning(request, "No seleccionó ningún comprobante para validar.")
            return redirect('comprobante_list')

        # Límite por ejecución web para proteger contra timeouts
        limite = 50
        try:
            if request.POST.get('limite'):
                limite = min(max(int(request.POST.get('limite')), 1), 200)
        except ValueError:
            limite = 50

        ip = get_client_ip(request)
        service = ValidacionMasivaService(ip_origen=ip)

        resumen = service.procesar_lote(
            usuario=user,
            comprobantes_ids=comprobantes_ids if not validar_todos else None,
            todos_pendientes=validar_todos,
            limite=limite,
            revalidar_aceptados=revalidar_aceptados,
        )

        # Almacenar reporte en sesión para ser renderizado en la interfaz con Bootstrap
        request.session['resumen_validacion_masiva'] = resumen.to_dict()

        if resumen.total_procesados == 0:
            if resumen.omitidos_por_aceptados > 0:
                messages.info(
                    request,
                    f"Se omitieron {resumen.omitidos_por_aceptados} comprobante(s) porque ya se encontraban en estado ACEPTADO."
                )
            else:
                messages.info(request, "No se encontraron comprobantes pendientes para procesar.")
        else:
            msg = (
                f"Procesamiento masivo finalizado con éxito: {resumen.total_procesados} comprobante(s) procesados. "
                f"(Aceptados: {resumen.aceptados}, Observados: {resumen.observados}, "
                f"Rechazados: {resumen.rechazados}, Error Consulta: {resumen.errores_consulta})"
            )
            if resumen.omitidos_por_aceptados > 0:
                msg += f" [Se omitieron {resumen.omitidos_por_aceptados} que ya estaban aceptados]"

            messages.success(request, msg)

        return redirect('comprobante_list')

    def get(self, request, *args, **kwargs):
        """Redireccionar al listado si se accede vía GET."""
        return redirect('comprobante_list')


class HistorialValidacionesListView(LoginRequiredMixin, ListView):
    """
    Vista de listado y consulta del historial de validaciones ante SUNAT.
    Permite filtrar por:
    - Fecha (rango desde / hasta)
    - Estado (Aceptado, Observado, Rechazado, Error de Consulta, Pendiente)
    - Usuario
    - RUC
    - Serie
    Utiliza paginación (15 registros por página) para evitar sobrecarga.
    """
    model = ValidacionSunat
    template_name = 'validaciones/historial_list.html'
    context_object_name = 'validaciones'
    paginate_by = 15

    def get_queryset(self):
        qs = ValidacionSunat.objects.select_related(
            'comprobante',
            'comprobante__usuario_registro',
            'usuario'
        ).order_by('-fecha_validacion', '-id')

        form = ValidacionFilterForm(self.request.GET)
        if form.is_valid():
            desde = form.cleaned_data.get('fecha_desde')
            hasta = form.cleaned_data.get('fecha_hasta')
            estado = form.cleaned_data.get('estado')
            usuario = form.cleaned_data.get('usuario')
            ruc = form.cleaned_data.get('ruc')
            serie = form.cleaned_data.get('serie')

            if desde:
                qs = qs.filter(fecha_validacion__date__gte=desde)
            if hasta:
                qs = qs.filter(fecha_validacion__date__lte=hasta)
            if estado:
                qs = qs.filter(
                    Q(estado_sunat__icontains=estado) |
                    Q(comprobante__estado=estado)
                )
            if usuario:
                qs = qs.filter(usuario=usuario)
            if ruc:
                qs = qs.filter(comprobante__ruc_emisor__icontains=ruc.strip())
            if serie:
                qs = qs.filter(comprobante__serie__iexact=serie.strip())

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['filter_form'] = ValidacionFilterForm(self.request.GET)

        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['query_params'] = params.urlencode()

        context['total_filtrados'] = self.get_queryset().count()
        context['total_global'] = ValidacionSunat.objects.count()

        # Resumen rápido de conteos para métricas
        context['conteo_aceptadas'] = ValidacionSunat.objects.filter(estado_sunat__icontains='Aceptado').count()
        context['conteo_observadas'] = ValidacionSunat.objects.filter(estado_sunat__icontains='Observado').count()
        context['conteo_rechazadas'] = ValidacionSunat.objects.filter(
            Q(estado_sunat__icontains='Rechazado') | Q(codigo_respuesta__in=['0', '2'])
        ).count()
        context['conteo_errores'] = ValidacionSunat.objects.filter(
            Q(estado_sunat__icontains='ERROR') | Q(codigo_respuesta__startswith='ERR')
        ).count()

        return context
