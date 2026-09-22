from datetime import datetime
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Sum, Q, Prefetch
from django.http import HttpResponse
from django.views import View
from django.views.generic import ListView

from apps.auditoria.services import AuditoriaService
from apps.comprobantes.models import Comprobante
from apps.validaciones.models import ValidacionSunat
from .forms import ReporteFiltroForm
from .models import ReporteGenerado
from .services import ExportadorExcelService, ExportadorPdfService


def obtener_queryset_reporte_filtrado(request):
    """
    Función utilitaria compartida que aplica los 7 filtros sobre los comprobantes
    y optimiza la carga con select_related y prefetch_related para evitar N+1 queries.
    """
    qs = Comprobante.objects.select_related('usuario_registro').prefetch_related(
        Prefetch(
            'validaciones',
            queryset=ValidacionSunat.objects.select_related('usuario').order_by('-fecha_validacion'),
            to_attr='validaciones_list'
        )
    ).all()

    form = ReporteFiltroForm(request.GET)
    resumen_filtros = []
    filtros_dict = {}

    if form.is_valid():
        fecha_inicio = form.cleaned_data.get('fecha_inicio')
        fecha_fin = form.cleaned_data.get('fecha_fin')
        ruc = form.cleaned_data.get('ruc')
        estado = form.cleaned_data.get('estado')
        tipo_comprobante = form.cleaned_data.get('tipo_comprobante')
        serie = form.cleaned_data.get('serie')
        usuario = form.cleaned_data.get('usuario')

        if fecha_inicio:
            qs = qs.filter(fecha_emision__gte=fecha_inicio)
            resumen_filtros.append(f"Desde: {fecha_inicio.strftime('%d/%m/%Y')}")
            filtros_dict['fecha_inicio'] = str(fecha_inicio)

        if fecha_fin:
            qs = qs.filter(fecha_emision__lte=fecha_fin)
            resumen_filtros.append(f"Hasta: {fecha_fin.strftime('%d/%m/%Y')}")
            filtros_dict['fecha_fin'] = str(fecha_fin)

        if ruc:
            qs = qs.filter(ruc_emisor__icontains=ruc.strip())
            resumen_filtros.append(f"RUC: {ruc.strip()}")
            filtros_dict['ruc'] = ruc.strip()

        if estado:
            qs = qs.filter(estado=estado)
            resumen_filtros.append(f"Estado: {estado}")
            filtros_dict['estado'] = estado

        if tipo_comprobante:
            qs = qs.filter(tipo_comprobante=tipo_comprobante)
            resumen_filtros.append(f"Tipo: {tipo_comprobante}")
            filtros_dict['tipo_comprobante'] = tipo_comprobante

        if serie:
            qs = qs.filter(serie__icontains=serie.strip().upper())
            resumen_filtros.append(f"Serie: {serie.strip().upper()}")
            filtros_dict['serie'] = serie.strip().upper()

        if usuario:
            qs = qs.filter(
                Q(usuario_registro=usuario) |
                Q(validaciones__usuario=usuario)
            ).distinct()
            resumen_filtros.append(f"Usuario: {usuario.username}")
            filtros_dict['usuario'] = usuario.username

    resumen_str = " | ".join(resumen_filtros) if resumen_filtros else "Sin filtros (Todos los comprobantes)"
    return qs.order_by('-fecha_emision', '-id'), form, resumen_str, filtros_dict


class ReporteComprobantesView(LoginRequiredMixin, ListView):
    """
    Vista en pantalla del módulo de Reportes de Comprobantes.
    Muestra resultados paginados, métricas globales de la búsqueda y enlaces para exportar.
    """
    model = Comprobante
    template_name = 'reportes/reporte_comprobantes.html'
    context_object_name = 'comprobantes'
    paginate_by = 25

    def get_queryset(self):
        qs, self.form, self.resumen_filtros, self.filtros_dict = obtener_queryset_reporte_filtrado(self.request)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs_completo = self.get_queryset()

        context['form'] = self.form
        context['resumen_filtros'] = self.resumen_filtros

        # Preservar parámetros GET en enlaces de paginación y exportación
        params = self.request.GET.copy()
        if 'page' in params:
            params.pop('page')
        context['url_params'] = params.urlencode()

        # Métricas agregadas sobre el queryset filtrado completo
        metricas = qs_completo.aggregate(
            total=Count('id'),
            monto_total=Sum('monto'),
            aceptados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.ACEPTADO)),
            observados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.OBSERVADO)),
            rechazados=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.RECHAZADO)),
            pendientes=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.PENDIENTE)),
            errores=Count('id', filter=Q(estado=Comprobante.EstadoComprobante.ERROR_CONSULTA)),
        )

        context['total_registros'] = metricas['total'] or 0
        context['monto_total'] = metricas['monto_total'] or 0
        context['total_aceptados'] = metricas['aceptados'] or 0
        context['total_observados'] = metricas['observados'] or 0
        context['total_rechazados'] = metricas['rechazados'] or 0
        context['total_pendientes'] = metricas['pendientes'] or 0
        context['total_errores'] = metricas['errores'] or 0
        context['filtro_activo'] = bool(self.filtros_dict)

        return context


class ReporteExportarExcelView(LoginRequiredMixin, View):
    """
    Genera y descarga el archivo Excel (.xlsx) con los 10 campos requeridos:
    RUC, TIPO, SERIE, NUMERO, FECHA EMISION, MONTO, ESTADO, FECHA VALIDACION, MENSAJE, USUARIO.
    Registra la exportación en la bitácora de auditoría.
    """
    def get(self, request, *args, **kwargs):
        qs, form, resumen_str, filtros_dict = obtener_queryset_reporte_filtrado(request)
        total_items = qs.count()

        # Generar archivo Excel
        excel_buffer = ExportadorExcelService.generar_excel(
            comprobantes=qs,
            titulo="Reporte de Comprobantes Electrónicos"
        )

        # Registrar en Auditoría (PASO 14: Registro obligatorio de exportaciones)
        AuditoriaService.registrar(
            usuario=request.user,
            accion='EXPORTAR_REPORTE',
            objeto_afectado=f"Reporte Excel ({total_items} comprobantes)",
            id_objeto='reporte_excel',
            descripcion=f"Exportación a Excel (.xlsx) de {total_items} comprobantes. Filtros: {resumen_str}",
            resultado='EXITOSO',
            request=request
        )

        # Registrar en el historial de reportes generados
        try:
            ReporteGenerado.objects.create(
                usuario=request.user,
                tipo_reporte=ReporteGenerado.TipoReporte.EXCEL,
                titulo=f"Reporte de Comprobantes ({total_items} registros)",
                filtros_aplicados=filtros_dict
            )
        except Exception:
            pass

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(
            excel_buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="reporte_comprobantes_{timestamp}.xlsx"'
        return response


class ReporteExportarPdfView(LoginRequiredMixin, View):
    """
    Genera y descarga el archivo PDF corporativo en orientación apaisada (Landscape).
    Registra la exportación en la bitácora de auditoría.
    """
    def get(self, request, *args, **kwargs):
        qs, form, resumen_str, filtros_dict = obtener_queryset_reporte_filtrado(request)
        total_items = qs.count()

        # Generar archivo PDF
        pdf_buffer = ExportadorPdfService.generar_pdf(
            comprobantes=qs,
            titulo="Reporte de Comprobantes Electrónicos",
            resumen_filtros=resumen_str
        )

        # Registrar en Auditoría (PASO 14: Registro obligatorio de exportaciones)
        AuditoriaService.registrar(
            usuario=request.user,
            accion='EXPORTAR_REPORTE',
            objeto_afectado=f"Reporte PDF ({total_items} comprobantes)",
            id_objeto='reporte_pdf',
            descripcion=f"Exportación a PDF de {total_items} comprobantes. Filtros: {resumen_str}",
            resultado='EXITOSO',
            request=request
        )

        # Registrar en el historial de reportes generados
        try:
            ReporteGenerado.objects.create(
                usuario=request.user,
                tipo_reporte=ReporteGenerado.TipoReporte.PDF,
                titulo=f"Reporte de Comprobantes ({total_items} registros)",
                filtros_aplicados=filtros_dict
            )
        except Exception:
            pass

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="reporte_comprobantes_{timestamp}.pdf"'
        return response
