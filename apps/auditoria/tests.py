from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import AuditoriaService, sanitizar_texto
from apps.comprobantes.models import Comprobante
from apps.importaciones.models import LoteImportacion

User = get_user_model()


class AuditoriaSeguridadYSanitizacionTests(TestCase):
    """
    Pruebas unitarias para verificar la sanitización estricta de datos confidenciales.
    Nunca deben almacenarse contraseñas, tokens SUNAT, client secrets ni credenciales.
    """

    def test_sanitizar_contrasenas(self):
        texto = "Error de autenticación con password: MiSuperPassword123! para el usuario admin"
        limpio = sanitizar_texto(texto)
        self.assertNotIn("MiSuperPassword123!", limpio)
        self.assertIn("[PROTEGIDO]", limpio)

    def test_sanitizar_tokens_sunat_y_bearer(self):
        texto = "Llamada HTTP con Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.token1234567890.signature"
        limpio = sanitizar_texto(texto)
        self.assertNotIn("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", limpio)
        self.assertIn("PROTEGIDO", limpio)

    def test_sanitizar_client_secret(self):
        texto = "Configuración cargada client_secret=abcdef1234567890secretkey y client_id=mi-client-id"
        limpio = sanitizar_texto(texto)
        self.assertNotIn("abcdef1234567890secretkey", limpio)
        self.assertIn("[PROTEGIDO]", limpio)

    def test_servicio_auditoria_registra_con_campos_completos(self):
        user = User.objects.create_user(username='admin_test', password='password123', role='ADMINISTRADOR')
        reg = AuditoriaService.registrar(
            usuario=user,
            accion=RegistroAuditoria.AccionAuditoria.LOGIN,
            objeto_afectado="Usuario admin_test",
            id_objeto=str(user.id),
            descripcion="password: secret123 acceso correcto",
            resultado='EXITOSO',
            ip_origen='192.168.1.100'
        )

        self.assertIsNotNone(reg)
        self.assertEqual(reg.usuario, user)
        self.assertEqual(reg.accion, 'LOGIN')
        self.assertEqual(reg.id_objeto, str(user.id))
        self.assertEqual(reg.resultado, 'EXITOSO')
        self.assertEqual(reg.ip_origen, '192.168.1.100')
        self.assertNotIn('secret123', reg.descripcion)
        self.assertIn('[PROTEGIDO]', reg.descripcion)


class AuditoriaControlAccesoYVistasTests(TestCase):
    """
    Pruebas de control de acceso a la pantalla de auditoría:
    Únicamente usuarios autorizados (ADMINISTRADOR / superusuario) pueden consultar la auditoría.
    """

    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username='admin_user',
            password='AdminPassword123!',
            role='ADMINISTRADOR'
        )
        self.trabajador_user = User.objects.create_user(
            username='trabajador_user',
            password='TrabajadorPassword123!',
            role='TRABAJADOR'
        )
        self.supervisor_user = User.objects.create_user(
            username='supervisor_user',
            password='SupervisorPassword123!',
            role='SUPERVISOR'
        )

        # Sembrar registros de auditoría
        for i in range(25):
            RegistroAuditoria.objects.create(
                usuario=self.admin_user if i % 2 == 0 else self.trabajador_user,
                accion='LOGIN' if i % 3 == 0 else 'REGISTRAR_COMPROBANTE',
                objeto_afectado=f"Recurso #{i}",
                id_objeto=str(i),
                descripcion=f"Acción de prueba #{i}",
                resultado='EXITOSO' if i % 4 != 0 else 'ERROR',
                ip_origen='127.0.0.1'
            )

    def test_acceso_anonimo_redirige_a_login(self):
        url = reverse('auditoria_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('login'), resp.url)

    def test_trabajador_denegado_acceso_auditoria(self):
        self.client.login(username='trabajador_user', password='TrabajadorPassword123!')
        url = reverse('auditoria_list')
        resp = self.client.get(url, follow=True)
        # Debe redirigir al dashboard con mensaje de error
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acceso restringido")

    def test_supervisor_denegado_acceso_auditoria(self):
        self.client.login(username='supervisor_user', password='SupervisorPassword123!')
        url = reverse('auditoria_list')
        resp = self.client.get(url, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acceso restringido")

    def test_administrador_acceso_permitido(self):
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_list')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'auditoria/auditoria_list.html')
        self.assertIn('registros', resp.context)
        self.assertEqual(len(resp.context['registros']), 20)  # Paginate 20

    def test_paginacion_auditoria(self):
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_list') + '?page=2'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        # 25 total en setUp, página 2 debe tener 5
        self.assertEqual(len(resp.context['registros']), 5)

    def test_filtro_por_usuario(self):
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_list') + f'?usuario={self.trabajador_user.id}'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        for reg in resp.context['registros']:
            self.assertEqual(reg.usuario, self.trabajador_user)

    def test_filtro_por_accion(self):
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_list') + '?accion=LOGIN'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        for reg in resp.context['registros']:
            self.assertEqual(reg.accion, 'LOGIN')

    def test_filtro_por_fecha(self):
        hoy = date.today()
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_list') + f'?fecha_desde={hoy}&fecha_hasta={hoy}'
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(len(resp.context['registros']) > 0)

    def test_exportar_auditoria_csv_y_registro_accion(self):
        self.client.login(username='admin_user', password='AdminPassword123!')
        url = reverse('auditoria_exportar_csv')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn('attachment; filename="auditoria_sistema_', resp['Content-Disposition'])

        # Comprobar que se registró la acción EXPORTAR_REPORTE
        audit = RegistroAuditoria.objects.filter(accion='EXPORTAR_REPORTE').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.usuario, self.admin_user)
        self.assertEqual(audit.resultado, 'EXITOSO')


class RegistroAccionesPrincipalesTests(TestCase):
    """
    Verifica que las 7 acciones principales queden registradas con los datos requeridos:
    LOGIN, REGISTRAR_COMPROBANTE, EDITAR_COMPROBANTE, IMPORTAR_ARCHIVO,
    VALIDAR_COMPROBANTE, VALIDACION_MASIVA, EXPORTAR_REPORTE.
    """

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='operador',
            password='OperadorPass123!',
            role='ADMINISTRADOR'
        )

    def test_accion_login_registrada(self):
        # Ejecutar login vía formulario
        resp = self.client.post(reverse('login'), {
            'username': 'operador',
            'password': 'OperadorPass123!'
        })
        self.assertEqual(resp.status_code, 302)

        audit = RegistroAuditoria.objects.filter(accion='LOGIN', usuario=self.user).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.resultado, 'EXITOSO')
        self.assertEqual(audit.id_objeto, str(self.user.id))
        self.assertIn("Usuario operador", audit.objeto_afectado)

    def test_accion_registrar_comprobante_registrada(self):
        self.client.login(username='operador', password='OperadorPass123!')
        url = reverse('comprobante_create')
        data = {
            'tipo_comprobante': '01',
            'serie': 'F001',
            'numero': 888,
            'ruc_emisor': '20123456789',
            'fecha_emision': date.today(),
            'monto': 250.00,
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        cp = Comprobante.objects.get(serie='F001', numero=888)
        audit = RegistroAuditoria.objects.filter(accion='REGISTRAR_COMPROBANTE', id_objeto=str(cp.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.usuario, self.user)
        self.assertEqual(audit.resultado, 'EXITOSO')
        self.assertIn(f"Comprobante {cp.codigo_completo}", audit.objeto_afectado)

    def test_accion_editar_comprobante_registrada(self):
        cp = Comprobante.objects.create(
            tipo_comprobante='01',
            serie='F001',
            numero=999,
            ruc_emisor='20123456789',
            fecha_emision=date.today(),
            monto=300.00,
            estado='PENDIENTE',
            usuario_registro=self.user
        )

        self.client.login(username='operador', password='OperadorPass123!')
        url = reverse('comprobante_update', kwargs={'pk': cp.pk})
        data = {
            'tipo_comprobante': '01',
            'serie': 'F001',
            'numero': 999,
            'ruc_emisor': '20123456789',
            'fecha_emision': date.today(),
            'monto': 350.00,
        }
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302)

        audit = RegistroAuditoria.objects.filter(accion='EDITAR_COMPROBANTE', id_objeto=str(cp.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.usuario, self.user)
        self.assertEqual(audit.resultado, 'EXITOSO')

    def test_accion_importar_archivo_registrada(self):
        from apps.importaciones.services import ImportacionService
        from django.core.files.uploadedfile import SimpleUploadedFile

        csv_content = (
            "RUC,TIPO,SERIE,NUMERO,FECHA,MONTO\n"
            "20123456789,01,F002,101,2026-09-01,100.00\n"
        ).encode('utf-8')
        archivo = SimpleUploadedFile("comprobantes_test.csv", csv_content, content_type="text/csv")

        lote = LoteImportacion.objects.create(
            usuario=self.user,
            nombre_archivo="comprobantes_test.csv",
            archivo=archivo
        )

        servicio = ImportacionService(lote, ip_address='127.0.0.1')
        servicio.procesar()

        audit = RegistroAuditoria.objects.filter(accion='IMPORTAR_ARCHIVO', id_objeto=str(lote.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.usuario, self.user)
        self.assertEqual(audit.resultado, 'EXITOSO')
        self.assertIn("Lote #", audit.objeto_afectado)
