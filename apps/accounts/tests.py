from datetime import date, timedelta
import json
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.comprobantes.models import Comprobante
from apps.importaciones.models import LoteImportacion
from apps.validaciones.models import ValidacionSunat

User = get_user_model()


class DashboardViewTests(TestCase):
    """
    Pruebas exhaustivas para el Dashboard principal (PASO 13):
    - Redirección de usuarios anónimos.
    - Consulta agregada eficiente de los 6 estados de comprobantes.
    - Cálculo de comprobantes procesados hoy.
    - Filtros por rango de fechas.
    - Inclusión de últimas validaciones e importaciones.
    - Formato JSON válido para los gráficos de Chart.js.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='admin_dashboard',
            password='AdminPass123!',
            role='ADMINISTRADOR'
        )

        hoy = date.today()
        hace_5_dias = hoy - timedelta(days=5)
        hace_10_dias = hoy - timedelta(days=10)

        # Crear comprobantes con distintos estados y fechas
        self.cp_pendiente = Comprobante.objects.create(
            tipo_comprobante='03', serie='B001', numero=1001,
            ruc_emisor='20111111111', fecha_emision=hoy, monto=100.00,
            estado=Comprobante.EstadoComprobante.PENDIENTE,
            usuario_registro=self.user
        )
        self.cp_aceptado = Comprobante.objects.create(
            tipo_comprobante='01', serie='F001', numero=1002,
            ruc_emisor='20222222222', fecha_emision=hace_5_dias, monto=250.00,
            estado=Comprobante.EstadoComprobante.ACEPTADO,
            usuario_registro=self.user
        )
        self.cp_observado = Comprobante.objects.create(
            tipo_comprobante='01', serie='F001', numero=1003,
            ruc_emisor='20333333333', fecha_emision=hace_5_dias, monto=300.00,
            estado=Comprobante.EstadoComprobante.OBSERVADO,
            usuario_registro=self.user
        )
        self.cp_rechazado = Comprobante.objects.create(
            tipo_comprobante='03', serie='B001', numero=1004,
            ruc_emisor='20444444444', fecha_emision=hace_10_dias, monto=80.00,
            estado=Comprobante.EstadoComprobante.RECHAZADO,
            usuario_registro=self.user
        )
        self.cp_error = Comprobante.objects.create(
            tipo_comprobante='03', serie='B001', numero=1005,
            ruc_emisor='20555555555', fecha_emision=hace_10_dias, monto=120.00,
            estado=Comprobante.EstadoComprobante.ERROR_CONSULTA,
            usuario_registro=self.user
        )

        # Crear validaciones: una hoy y otra en fecha pasada
        self.val_hoy = ValidacionSunat.objects.create(
            comprobante=self.cp_aceptado,
            estado_sunat='Aceptado',
            codigo_respuesta='1',
            mensaje='Comprobante existe y está aceptado.',
            usuario=self.user
        )
        self.val_pasada = ValidacionSunat.objects.create(
            comprobante=self.cp_observado,
            estado_sunat='Observado',
            codigo_respuesta='1',
            mensaje='Emisor observado.',
            usuario=self.user
        )
        # Ajustar fecha_validacion de la pasada a hace 5 días
        ValidacionSunat.objects.filter(pk=self.val_pasada.pk).update(
            fecha_validacion=timezone.now() - timedelta(days=5)
        )

        # Crear lote de importación
        self.lote = LoteImportacion.objects.create(
            usuario=self.user,
            nombre_archivo="carga_lote_test.csv",
            archivo=SimpleUploadedFile("carga_lote_test.csv", b"dummy content", content_type="text/csv"),
            total_leidos=10,
            importados_correctos=8,
            estado=LoteImportacion.EstadoLote.COMPLETADO
        )

    def test_dashboard_requiere_login(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

    def test_dashboard_renderiza_metricas_correctas(self):
        self.client.login(username='admin_dashboard', password='AdminPass123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

        ctx = resp.context
        self.assertEqual(ctx['total_comprobantes'], 5)
        self.assertEqual(ctx['aceptados'], 1)
        self.assertEqual(ctx['observados'], 1)
        self.assertEqual(ctx['rechazados'], 1)
        self.assertEqual(ctx['pendientes'], 1)
        self.assertEqual(ctx['errores'], 1)

        # Verificar etiquetas en HTML
        self.assertContains(resp, "TOTAL COMPROBANTES")
        self.assertContains(resp, "ACEPTADOS")
        self.assertContains(resp, "OBSERVADOS")
        self.assertContains(resp, "RECHAZADOS")
        self.assertContains(resp, "PENDIENTES")
        self.assertContains(resp, "ERROR DE CONSULTA")

    def test_dashboard_comprobantes_procesados_hoy(self):
        self.client.login(username='admin_dashboard', password='AdminPass123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

        # Solo val_hoy se ejecutó hoy
        self.assertEqual(resp.context['procesados_hoy'], 1)
        self.assertContains(resp, "Comprobantes procesados hoy")

    def test_dashboard_filtro_por_rango_fechas(self):
        self.client.login(username='admin_dashboard', password='AdminPass123!')
        hoy = date.today()
        hace_7_dias = hoy - timedelta(days=7)

        # Filtrar entre hace 7 días y hoy (debe excluir cp_rechazado y cp_error que son de hace 10 días)
        url = reverse('dashboard') + f'?fecha_desde={hace_7_dias}&fecha_hasta={hoy}'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        ctx = resp.context
        self.assertTrue(ctx['filtro_activo'])
        self.assertEqual(ctx['total_comprobantes'], 3)
        self.assertEqual(ctx['aceptados'], 1)
        self.assertEqual(ctx['observados'], 1)
        self.assertEqual(ctx['pendientes'], 1)
        self.assertEqual(ctx['rechazados'], 0)
        self.assertEqual(ctx['errores'], 0)

    def test_dashboard_ultimas_validaciones_e_importaciones(self):
        self.client.login(username='admin_dashboard', password='AdminPass123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

        ctx = resp.context
        self.assertIn('ultimas_validaciones', ctx)
        self.assertIn('ultimas_importaciones', ctx)
        self.assertTrue(len(ctx['ultimas_validaciones']) >= 2)
        self.assertTrue(len(ctx['ultimas_importaciones']) >= 1)

        self.assertContains(resp, "Últimas Validaciones ante SUNAT")
        self.assertContains(resp, "Últimas Importaciones")
        self.assertContains(resp, "carga_lote_test.csv")

    def test_dashboard_datos_graficos_json(self):
        self.client.login(username='admin_dashboard', password='AdminPass123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)

        # Verificar JSON de estados
        raw_estados = resp.context['chart_estados_json']
        estados_data = json.loads(raw_estados)
        self.assertIn('labels', estados_data)
        self.assertIn('data', estados_data)
        self.assertEqual(len(estados_data['labels']), 5)
        self.assertEqual(sum(estados_data['data']), 5)

        # Verificar JSON de fechas
        raw_fechas = resp.context['chart_fechas_json']
        fechas_data = json.loads(raw_fechas)
        self.assertIn('labels', fechas_data)
        self.assertIn('totales', fechas_data)

        # Verificar inclusión de Canvas de Chart.js y script en HTML
        self.assertContains(resp, 'id="chartEstadosCanvas"')
        self.assertContains(resp, 'id="chartFechasCanvas"')
        self.assertContains(resp, 'chart.js')
