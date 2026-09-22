"""
Pruebas unitarias para el módulo de integración oficial con SUNAT (services.sunat).
Verifica:
1. Endpoints, autenticación OAuth 2.0 y manejo de tokens.
2. Formato de payload según la especificación oficial de SUNAT.
3. Interpretación de códigos de respuesta (estadoCp, estadoRuc, condDomiRuc).
4. Manejo de excepciones, timeouts y reintentos por expiración de token.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from services.sunat import (
    SunatAuthError,
    SunatClient,
    SunatConfigError,
    SunatConnectionError,
    traducir_estado_sistema,
)
from services.sunat.constants import (
    CONDICION_DOMICILIO_RUC,
    ESTADO_CP,
    ESTADO_RUC,
    SUNAT_AUTH_URL_TEMPLATE,
    SUNAT_OAUTH_SCOPE,
    SUNAT_VALIDAR_URL_TEMPLATE,
)


class SunatIntegrationTests(TestCase):
    def setUp(self):
        self.ruc_empresa = "20600000001"
        self.client_id = "test-client-id-uuid"
        self.client_secret = "test-client-secret-key"
        self.client = SunatClient(
            ruc=self.ruc_empresa,
            client_id=self.client_id,
            client_secret=self.client_secret,
            modo="BETA",
        )

    def test_validacion_credenciales_faltantes(self):
        """Verifica que se lance SunatConfigError si faltan credenciales."""
        invalido = SunatClient(ruc="", client_id="", client_secret="")
        with self.assertRaises(SunatConfigError):
            invalido.obtener_token()

    @patch('requests.Session.post')
    def test_obtener_token_exitoso(self, mock_post):
        """Verifica la petición OAuth 2.0 con endpoints y parámetros oficiales."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token_valido_123456",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        token = self.client.obtener_token()

        self.assertEqual(token, "token_valido_123456")
        expected_url = SUNAT_AUTH_URL_TEMPLATE.format(client_id=self.client_id)
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], expected_url)
        self.assertEqual(kwargs['data']['grant_type'], 'client_credentials')
        self.assertEqual(kwargs['data']['scope'], SUNAT_OAUTH_SCOPE)
        self.assertEqual(kwargs['data']['client_id'], self.client_id)
        self.assertEqual(kwargs['data']['client_secret'], self.client_secret)

    @patch('requests.Session.post')
    def test_caching_token(self, mock_post):
        """Verifica que el token se almacene en memoria y no haga peticiones repetidas."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "token_cacheador",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        # Primera llamada obtiene el token
        t1 = self.client.obtener_token()
        # Segunda llamada debe retornar el mismo token sin hacer nueva petición HTTP
        t2 = self.client.obtener_token()

        self.assertEqual(t1, t2)
        self.assertEqual(mock_post.call_count, 1)

    @patch('requests.Session.post')
    def test_error_autenticacion_oauth(self, mock_post):
        """Verifica que un error 401 en autenticación lance SunatAuthError."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "unauthorized_client"}
        mock_post.return_value = mock_response

        with self.assertRaises(SunatAuthError):
            self.client.obtener_token()

    @patch('requests.Session.post')
    def test_validar_comprobante_aceptado(self, mock_post):
        """Verifica el envío y procesamiento de un comprobante válido y aceptado."""
        # 1. Mock de autenticación
        auth_resp = MagicMock()
        auth_resp.status_code = 200
        auth_resp.json.return_value = {"access_token": "tok_abc", "expires_in": 3600}

        # 2. Mock de validación
        val_resp = MagicMock()
        val_resp.status_code = 200
        val_resp.json.return_value = {
            "success": True,
            "message": "La consulta se realizó exitosamente.",
            "data": {
                "estadoCp": "1",
                "estadoRuc": "00",
                "condDomiRuc": "00",
                "observaciones": [],
            }
        }
        mock_post.side_effect = [auth_resp, val_resp]

        resultado = self.client.validar_comprobante(
            num_ruc="20100000009",
            cod_comp="01",
            numero_serie="F001",
            numero=1234,
            fecha_emision=date(2026, 9, 20),
            monto=250.75,
        )

        self.assertTrue(resultado.success)
        self.assertEqual(resultado.estado_cp, "1")
        self.assertEqual(resultado.estado_cp_desc, "Aceptado")
        self.assertEqual(resultado.estado_ruc, "00")
        self.assertEqual(resultado.estado_ruc_desc, "Activo")
        self.assertEqual(resultado.cond_domi_ruc, "00")
        self.assertEqual(resultado.cond_domi_ruc_desc, "Habido")
        self.assertEqual(resultado.estado_sistema, "ACEPTADO")

        # Verificar headers y endpoint de la segunda llamada (validación)
        val_call = mock_post.call_args_list[1]
        expected_url = SUNAT_VALIDAR_URL_TEMPLATE.format(ruc=self.ruc_empresa)
        self.assertEqual(val_call[0][0], expected_url)
        self.assertEqual(val_call[1]['headers']['Authorization'], 'Bearer tok_abc')
        self.assertEqual(val_call[1]['json']['fechaEmision'], '20/09/2026')
        self.assertEqual(val_call[1]['json']['monto'], '250.75')

    @patch('requests.Session.post')
    def test_validar_comprobante_observado_no_habido(self, mock_post):
        """Verifica que un comprobante aceptado con emisor No Habido resulte en OBSERVADO."""
        auth_resp = MagicMock(status_code=200)
        auth_resp.json.return_value = {"access_token": "tok_123", "expires_in": 3600}

        val_resp = MagicMock(status_code=200)
        val_resp.json.return_value = {
            "success": True,
            "data": {
                "estadoCp": "1",
                "estadoRuc": "00",
                "condDomiRuc": "12",  # No habido
                "observaciones": ["El emisor se encuentra en condición de No Habido."],
            }
        }
        mock_post.side_effect = [auth_resp, val_resp]

        resultado = self.client.validar_comprobante(
            num_ruc="20100000009",
            cod_comp="01",
            numero_serie="F001",
            numero=100,
            fecha_emision="2026-09-15",
            monto="150.00",
        )

        self.assertTrue(resultado.success)
        self.assertEqual(resultado.estado_sistema, "OBSERVADO")
        self.assertEqual(resultado.cond_domi_ruc, "12")
        self.assertEqual(resultado.cond_domi_ruc_desc, "No habido")

    @patch('requests.Session.post')
    def test_validar_comprobante_no_existe_o_anulado(self, mock_post):
        """Verifica que estadoCp 0 o 2 se traduzca a RECHAZADO."""
        self.assertEqual(traducir_estado_sistema('0'), 'RECHAZADO')
        self.assertEqual(traducir_estado_sistema('2'), 'RECHAZADO')
        self.assertEqual(traducir_estado_sistema('4'), 'RECHAZADO')

    @patch('requests.Session.post')
    def test_error_422_sunat(self, mock_post):
        """Verifica manejo de errores HTTP 422 de formato/validación en SUNAT."""
        auth_resp = MagicMock(status_code=200)
        auth_resp.json.return_value = {"access_token": "tok_abc", "expires_in": 3600}

        err_resp = MagicMock(status_code=422)
        err_resp.json.return_value = {
            "cod": "422",
            "msg": "Número de comprobante inválido",
        }
        mock_post.side_effect = [auth_resp, err_resp]

        resultado = self.client.validar_comprobante(
            num_ruc="20100000009",
            cod_comp="01",
            numero_serie="F001",
            numero=999999,
            fecha_emision="01/01/2026",
            monto="50.00",
        )

        self.assertFalse(resultado.success)
        self.assertEqual(resultado.estado_sistema, "ERROR_CONSULTA")
        self.assertEqual(resultado.http_status, 422)
        self.assertIn("Número de comprobante inválido", resultado.mensaje)


from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.comprobantes.models import Comprobante
from apps.validaciones.models import ValidacionSunat
from apps.auditoria.models import RegistroAuditoria
from apps.validaciones.services import ValidacionComprobanteService

User = get_user_model()


class ValidacionIndividualPaso9Tests(TestCase):
    """
    Pruebas exhaustivas para el PASO 9:
    1. Obtener los datos del comprobante.
    2. Validar los datos localmente.
    3. Consultar el servicio oficial de SUNAT.
    4. Recibir la respuesta.
    5. Interpretar la respuesta.
    6. Guardar una nueva ValidacionSunat.
    7. Actualizar el estado actual del comprobante.
    8. Registrar usuario, fecha, código y mensaje.
    9. Registrar la acción en auditoría.
    10. Conservar historial y verificar que errores de conexión/auth NO rechazan.
    """

    def setUp(self):
        self.trabajador = User.objects.create_user(
            username='trabajador1',
            password='Password123!',
            role=User.Role.TRABAJADOR
        )
        self.supervisor = User.objects.create_user(
            username='supervisor1',
            password='Password123!',
            role=User.Role.SUPERVISOR
        )
        self.comprobante = Comprobante.objects.create(
            ruc_emisor='20123456789',
            tipo_comprobante='01',
            serie='F001',
            numero=1001,
            fecha_emision=date(2026, 9, 20),
            monto=150.00,
            estado=Comprobante.EstadoComprobante.PENDIENTE,
            usuario_registro=self.trabajador
        )

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_flujo_completo_aceptado(self, mock_validar):
        """Paso 9: Flujo exitoso con respuesta ACEPTADO."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True,
            estado_cp='1',
            estado_cp_desc='Aceptado',
            estado_ruc='00',
            estado_ruc_desc='Activo',
            cond_domi_ruc='00',
            cond_domi_ruc_desc='Habido',
            observaciones=[],
            estado_sistema='ACEPTADO',
            mensaje='La consulta se realizó exitosamente.',
            http_status=200,
            raw_response={'data': {'estadoCp': '1'}}
        )

        service = ValidacionComprobanteService(ip_origen='192.168.1.100')
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.estado_comprobante, Comprobante.EstadoComprobante.ACEPTADO)

        # 7. Actualizar el estado actual del comprobante
        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.ACEPTADO)

        # 6 y 8. Guardar nueva ValidacionSunat con usuario, fecha, código y mensaje
        val = ValidacionSunat.objects.filter(comprobante=self.comprobante).first()
        self.assertIsNotNone(val)
        self.assertEqual(val.codigo_respuesta, '1')
        self.assertEqual(val.usuario, self.trabajador)
        self.assertIn('Aceptado', val.estado_sunat)

        # 9. Registrar acción en auditoría
        audit = RegistroAuditoria.objects.filter(objeto_afectado=f"Comprobante {self.comprobante.codigo_completo}").first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.usuario, self.trabajador)
        self.assertEqual(audit.ip_origen, '192.168.1.100')
        self.assertIn('ACEPTADO', audit.accion)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_flujo_completo_observado(self, mock_validar):
        """Paso 9: Emisor No Habido resulta en OBSERVADO."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True,
            estado_cp='1',
            estado_cp_desc='Aceptado',
            estado_ruc='00',
            estado_ruc_desc='Activo',
            cond_domi_ruc='12',
            cond_domi_ruc_desc='No habido',
            observaciones=['Emisor no habido'],
            estado_sistema='OBSERVADO',
            mensaje='Comprobante con observaciones.',
            http_status=200
        )

        service = ValidacionComprobanteService()
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.estado_comprobante, Comprobante.EstadoComprobante.OBSERVADO)
        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.OBSERVADO)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_flujo_completo_rechazado_por_anulacion(self, mock_validar):
        """Paso 9: Comprobante anulado (estadoCp=2) resulta en RECHAZADO."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True,
            estado_cp='2',
            estado_cp_desc='Anulado',
            estado_ruc='00',
            estado_ruc_desc='Activo',
            cond_domi_ruc='00',
            cond_domi_ruc_desc='Habido',
            estado_sistema='RECHAZADO',
            mensaje='El comprobante fue dado de baja.',
            http_status=200
        )

        service = ValidacionComprobanteService()
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertTrue(resultado.exito)
        self.assertEqual(resultado.estado_comprobante, Comprobante.EstadoComprobante.RECHAZADO)
        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.RECHAZADO)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_timeout_de_conexion_no_es_rechazado(self, mock_validar):
        """
        REGLA CRÍTICA:
        Un timeout o error de red NO significa RECHAZADO, sino ERROR_CONSULTA.
        """
        mock_validar.side_effect = SunatConnectionError("Timeout de conexión al servicio de SUNAT")

        service = ValidacionComprobanteService()
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.estado_comprobante, Comprobante.EstadoComprobante.ERROR_CONSULTA)

        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.ERROR_CONSULTA)
        self.assertNotEqual(self.comprobante.estado, Comprobante.EstadoComprobante.RECHAZADO)

        # Historial y auditoría registrados
        val = ValidacionSunat.objects.filter(comprobante=self.comprobante).first()
        self.assertIsNotNone(val)
        self.assertEqual(val.codigo_respuesta, 'ERR_CONEXION')

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_error_autenticacion_no_es_rechazado(self, mock_validar):
        """
        REGLA CRÍTICA:
        Fallo de autenticación o token OAuth 2.0 NO significa RECHAZADO, sino ERROR_CONSULTA.
        """
        mock_validar.side_effect = SunatAuthError("Credenciales de API inválidas", http_status=401)

        service = ValidacionComprobanteService()
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.estado_comprobante, Comprobante.EstadoComprobante.ERROR_CONSULTA)

        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.ERROR_CONSULTA)
        self.assertNotEqual(self.comprobante.estado, Comprobante.EstadoComprobante.RECHAZADO)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_conserva_historial_validaciones_anteriores(self, mock_validar):
        """Conserva siempre el historial de validaciones (1 a N)."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True,
            estado_cp='1',
            estado_cp_desc='Aceptado',
            estado_sistema='ACEPTADO',
            mensaje='OK',
            http_status=200
        )

        service = ValidacionComprobanteService()
        # Primera validación
        service.ejecutar_validacion(self.comprobante.id, self.trabajador)
        # Segunda validación (revalidación)
        service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertEqual(self.comprobante.validaciones.count(), 2)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_validacion_local_falla_sin_consultar_sunat(self, mock_validar):
        """Paso 2: Si los datos locales son inválidos, no se consulta SUNAT."""
        # Forzar RUC corrupto a 5 dígitos
        Comprobante.objects.filter(id=self.comprobante.id).update(ruc_emisor='12345')

        service = ValidacionComprobanteService()
        resultado = service.ejecutar_validacion(self.comprobante.id, self.trabajador)

        self.assertFalse(resultado.exito)
        self.assertEqual(resultado.codigo_respuesta, 'VAL_LOCAL')
        mock_validar.assert_not_called()

        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.ERROR_CONSULTA)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_vista_validar_comprobante_post_exitoso(self, mock_validar):
        """Prueba de la vista HTTP POST con usuario autenticado (Trabajador)."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True,
            estado_cp='1',
            estado_cp_desc='Aceptado',
            estado_sistema='ACEPTADO',
            mensaje='Aceptado por SUNAT.',
            http_status=200
        )

        self.client.force_login(self.trabajador)
        url = reverse('comprobante_validar', kwargs={'pk': self.comprobante.pk})
        response = self.client.post(url)

        # Debe redirigir al detalle del comprobante
        self.assertRedirects(response, reverse('comprobante_detail', kwargs={'pk': self.comprobante.pk}))

        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.ACEPTADO)

    def test_vista_supervisor_sin_permiso(self):
        """El rol Supervisor solo tiene permiso de lectura y no puede validar."""
        self.client.force_login(self.supervisor)
        url = reverse('comprobante_validar', kwargs={'pk': self.comprobante.pk})
        response = self.client.post(url)

        self.assertRedirects(response, reverse('comprobante_detail', kwargs={'pk': self.comprobante.pk}))
        self.comprobante.refresh_from_db()
        self.assertEqual(self.comprobante.estado, Comprobante.EstadoComprobante.PENDIENTE)
        self.assertEqual(self.comprobante.validaciones.count(), 0)


from io import StringIO
from django.core.management import call_command
from apps.validaciones.services import ValidacionMasivaService


class ValidacionMasivaPaso10Tests(TestCase):
    """
    Pruebas para el PASO 10: Validación masiva de comprobantes.
    """

    def setUp(self):
        self.trabajador = User.objects.create_user(
            username='trabajador_masivo',
            password='Password123!',
            role=User.Role.TRABAJADOR
        )
        self.supervisor = User.objects.create_user(
            username='supervisor_masivo',
            password='Password123!',
            role=User.Role.SUPERVISOR
        )

        # Crear lote de comprobantes para pruebas
        self.cp1 = Comprobante.objects.create(
            ruc_emisor='20100000001', tipo_comprobante='01', serie='F001', numero=1,
            fecha_emision=date(2026, 9, 1), monto=100.0, estado=Comprobante.EstadoComprobante.PENDIENTE
        )
        self.cp2 = Comprobante.objects.create(
            ruc_emisor='20100000002', tipo_comprobante='01', serie='F001', numero=2,
            fecha_emision=date(2026, 9, 2), monto=200.0, estado=Comprobante.EstadoComprobante.PENDIENTE
        )
        self.cp3 = Comprobante.objects.create(
            ruc_emisor='20100000003', tipo_comprobante='03', serie='B001', numero=3,
            fecha_emision=date(2026, 9, 3), monto=300.0, estado=Comprobante.EstadoComprobante.PENDIENTE
        )
        self.cp_aceptado = Comprobante.objects.create(
            ruc_emisor='20100000004', tipo_comprobante='01', serie='F001', numero=4,
            fecha_emision=date(2026, 9, 4), monto=400.0, estado=Comprobante.EstadoComprobante.ACEPTADO
        )

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_validacion_masiva_con_conteo_estadistico(self, mock_validar):
        """
        Verifica el conteo exacto de TOTAL PROCESADOS, ACEPTADOS, OBSERVADOS, RECHAZADOS.
        """
        from services.sunat.client import SunatValidationResult

        # Mock respuestas:
        # cp1 -> ACEPTADO (estadoCp=1, ruc=00, dom=00)
        # cp2 -> OBSERVADO (estadoCp=1, dom=12 No habido)
        # cp3 -> RECHAZADO (estadoCp=2 Anulado)
        mock_validar.side_effect = [
            SunatValidationResult(
                success=True, estado_cp='1', estado_ruc='00', cond_domi_ruc='00',
                estado_sistema='ACEPTADO', mensaje='Comprobante Aceptado'
            ),
            SunatValidationResult(
                success=True, estado_cp='1', estado_ruc='00', cond_domi_ruc='12',
                estado_sistema='OBSERVADO', mensaje='Emisor No Habido'
            ),
            SunatValidationResult(
                success=True, estado_cp='2', estado_ruc='00', cond_domi_ruc='00',
                estado_sistema='RECHAZADO', mensaje='Comprobante Anulado'
            ),
        ]

        service = ValidacionMasivaService(delay_segundos=0, ip_origen='127.0.0.1')
        resumen = service.procesar_lote(
            usuario=self.trabajador,
            comprobantes_ids=[self.cp1.id, self.cp2.id, self.cp3.id]
        )

        self.assertEqual(resumen.total_procesados, 3)
        self.assertEqual(resumen.aceptados, 1)
        self.assertEqual(resumen.observados, 1)
        self.assertEqual(resumen.rechazados, 1)
        self.assertEqual(resumen.errores_consulta, 0)

        # Verificar estados en BD
        self.cp1.refresh_from_db()
        self.cp2.refresh_from_db()
        self.cp3.refresh_from_db()
        self.assertEqual(self.cp1.estado, Comprobante.EstadoComprobante.ACEPTADO)
        self.assertEqual(self.cp2.estado, Comprobante.EstadoComprobante.OBSERVADO)
        self.assertEqual(self.cp3.estado, Comprobante.EstadoComprobante.RECHAZADO)

        # Verificar auditoría consolidada
        audit = RegistroAuditoria.objects.filter(accion='Validación Masiva SUNAT').first()
        self.assertIsNotNone(audit)
        self.assertIn("Total: 3", audit.descripcion)
        self.assertIn("Aceptados: 1", audit.descripcion)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_omite_comprobantes_ya_aceptados_por_defecto(self, mock_validar):
        """
        Evita validar nuevamente comprobantes ya aceptados por defecto.
        """
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True, estado_cp='1', estado_sistema='ACEPTADO', mensaje='OK'
        )

        service = ValidacionMasivaService(delay_segundos=0)
        # Incluimos cp1 (PENDIENTE) y cp_aceptado (ACEPTADO)
        resumen = service.procesar_lote(
            usuario=self.trabajador,
            comprobantes_ids=[self.cp1.id, self.cp_aceptado.id],
            revalidar_aceptados=False
        )

        # Solo debe procesar cp1
        self.assertEqual(resumen.total_procesados, 1)
        self.assertEqual(resumen.omitidos_por_aceptados, 1)
        self.assertEqual(mock_validar.call_count, 1)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_continuidad_ante_error_de_red_sin_rechazar(self, mock_validar):
        """
        Si una consulta falla por timeout/red, debe continuar con las demás y NO marcar como RECHAZADO.
        """
        from services.sunat.client import SunatValidationResult

        # cp1 falla por conexión, cp2 se valida exitosamente
        mock_validar.side_effect = [
            SunatConnectionError("Timeout de conexión al servicio de SUNAT"),
            SunatValidationResult(
                success=True, estado_cp='1', estado_ruc='00', cond_domi_ruc='00',
                estado_sistema='ACEPTADO', mensaje='OK'
            )
        ]

        service = ValidacionMasivaService(delay_segundos=0)
        resumen = service.procesar_lote(
            usuario=self.trabajador,
            comprobantes_ids=[self.cp1.id, self.cp2.id]
        )

        self.assertEqual(resumen.total_procesados, 2)
        self.assertEqual(resumen.errores_consulta, 1)
        self.assertEqual(resumen.aceptados, 1)

        self.cp1.refresh_from_db()
        self.cp2.refresh_from_db()

        # cp1 NO debe ser RECHAZADO, sino ERROR_CONSULTA
        self.assertEqual(self.cp1.estado, Comprobante.EstadoComprobante.ERROR_CONSULTA)
        self.assertNotEqual(self.cp1.estado, Comprobante.EstadoComprobante.RECHAZADO)

        # cp2 fue procesado correctamente
        self.assertEqual(self.cp2.estado, Comprobante.EstadoComprobante.ACEPTADO)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_validar_todos_los_pendientes(self, mock_validar):
        """
        Prueba la opción 'Validar todos los pendientes'.
        """
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True, estado_cp='1', estado_sistema='ACEPTADO', mensaje='Aceptado'
        )

        service = ValidacionMasivaService(delay_segundos=0)
        resumen = service.procesar_lote(
            usuario=self.trabajador,
            todos_pendientes=True,
            limite=50
        )

        # Hay 3 comprobantes pendientes: cp1, cp2, cp3 (cp_aceptado no es pendiente)
        self.assertEqual(resumen.total_procesados, 3)
        self.assertEqual(resumen.aceptados, 3)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_vista_validar_masivo_post_seleccionados(self, mock_validar):
        """Prueba HTTP POST a la vista masiva con lista de IDs."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True, estado_cp='1', estado_sistema='ACEPTADO', mensaje='OK'
        )

        self.client.force_login(self.trabajador)
        url = reverse('comprobante_validar_masivo')
        response = self.client.post(url, {
            'comprobantes_ids': [self.cp1.id, self.cp2.id]
        }, follow=True)

        # Al seguir el redirect, ComprobanteListView extrae el resumen de la sesión al contexto
        self.assertRedirects(response, reverse('comprobante_list'))
        self.assertIn('resumen_masivo', response.context)
        resumen = response.context['resumen_masivo']
        self.assertIsNotNone(resumen)
        self.assertEqual(resumen['total_procesados'], 2)

    def test_vista_validar_masivo_supervisor_denegado(self):
        """El rol Supervisor no tiene permiso para ejecutar validación masiva."""
        self.client.force_login(self.supervisor)
        url = reverse('comprobante_validar_masivo')
        response = self.client.post(url, {
            'comprobantes_ids': [self.cp1.id]
        })

        self.assertRedirects(response, reverse('comprobante_list'))
        self.cp1.refresh_from_db()
        self.assertEqual(self.cp1.estado, Comprobante.EstadoComprobante.PENDIENTE)

    @patch('services.sunat.client.SunatClient.validar_comprobante')
    def test_comando_cli_validar_pendientes(self, mock_validar):
        """Prueba de ejecución del comando management validar_pendientes."""
        from services.sunat.client import SunatValidationResult

        mock_validar.return_value = SunatValidationResult(
            success=True, estado_cp='1', estado_sistema='ACEPTADO', mensaje='Comprobante Aceptado'
        )

        out = StringIO()
        call_command('validar_pendientes', limite=2, delay=0, stdout=out)
        output = out.getvalue()

        self.assertIn("RESULTADOS DEL PROCESAMIENTO MASIVO", output)
        self.assertIn("TOTAL PROCESADOS : 2", output)


class HistorialValidacionesPaso11Tests(TestCase):
    """
    Pruebas para el PASO 11: Historial de validaciones.
    - Cada comprobante debe mostrar todas las consultas realizadas a SUNAT.
    - Mostrar: Fecha y hora, Estado obtenido, Código de respuesta, Mensaje, Usuario, Resultado de consulta.
    - Nunca sobrescribir historial anterior.
    - Filtros por: Fecha, Estado, Usuario, RUC, Serie.
    - Paginación.
    """

    def setUp(self):
        self.user1 = User.objects.create_user(
            username='operador1',
            password='Password123!',
            role=User.Role.TRABAJADOR
        )
        self.user2 = User.objects.create_user(
            username='operador2',
            password='Password123!',
            role=User.Role.TRABAJADOR
        )

        self.cp1 = Comprobante.objects.create(
            ruc_emisor='20500000001',
            tipo_comprobante='01',
            serie='F001',
            numero=152,
            fecha_emision=date(2026, 9, 20),
            monto=150.00,
            estado=Comprobante.EstadoComprobante.PENDIENTE
        )
        self.cp2 = Comprobante.objects.create(
            ruc_emisor='20500000002',
            tipo_comprobante='03',
            serie='B001',
            numero=500,
            fecha_emision=date(2026, 9, 21),
            monto=80.00,
            estado=Comprobante.EstadoComprobante.PENDIENTE
        )

        # Crear registros históricos simulados
        self.val1 = ValidacionSunat.objects.create(
            comprobante=self.cp1,
            estado_sunat='Aceptado (ACEPTADO)',
            codigo_respuesta='1',
            mensaje='Comprobante validado correctamente.',
            usuario=self.user1,
            respuesta_sunat={'estadoCp': '1', 'estadoRuc': '00'}
        )
        self.val2 = ValidacionSunat.objects.create(
            comprobante=self.cp1,
            estado_sunat='ERROR_CONSULTA',
            codigo_respuesta='ERR_CONEXION',
            mensaje='Timeout de conexión con SUNAT.',
            usuario=self.user1,
            respuesta_sunat={'error': 'timeout'}
        )
        self.val3 = ValidacionSunat.objects.create(
            comprobante=self.cp2,
            estado_sunat='Rechazado (RECHAZADO)',
            codigo_respuesta='2',
            mensaje='Comprobante anulado por emisor.',
            usuario=self.user2,
            respuesta_sunat={'estadoCp': '2'}
        )

    def test_historial_requiere_login(self):
        """Usuario no autenticado debe ser redirigido al login."""
        url = reverse('historial_validaciones')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_historial_listado_completo(self):
        """Usuario autenticado puede consultar el historial completo."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'validaciones/historial_list.html')
        self.assertEqual(len(response.context['validaciones']), 3)

    def test_historial_filtro_por_estado(self):
        """Filtrar el historial por estado obtenido."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')

        response = self.client.get(url, {'estado': 'ACEPTADO'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['validaciones']), 1)
        self.assertEqual(response.context['validaciones'][0].id, self.val1.id)

        response_rechazado = self.client.get(url, {'estado': 'RECHAZADO'})
        self.assertEqual(len(response_rechazado.context['validaciones']), 1)
        self.assertEqual(response_rechazado.context['validaciones'][0].id, self.val3.id)

    def test_historial_filtro_por_ruc(self):
        """Filtrar el historial por RUC del emisor."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')

        response = self.client.get(url, {'ruc': '20500000001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['validaciones']), 2)

    def test_historial_filtro_por_serie(self):
        """Filtrar el historial por serie del comprobante."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')

        response = self.client.get(url, {'serie': 'B001'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['validaciones']), 1)
        self.assertEqual(response.context['validaciones'][0].comprobante.serie, 'B001')

    def test_historial_filtro_por_usuario(self):
        """Filtrar el historial por usuario consultante."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')

        response = self.client.get(url, {'usuario': self.user2.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['validaciones']), 1)
        self.assertEqual(response.context['validaciones'][0].usuario, self.user2)

    def test_historial_filtro_por_fecha(self):
        """Filtrar el historial por rango de fechas."""
        self.client.force_login(self.user1)
        url = reverse('historial_validaciones')

        hoy = date.today().strftime('%Y-%m-%d')
        response = self.client.get(url, {'fecha_desde': hoy, 'fecha_hasta': hoy})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['validaciones']), 3)

    def test_historial_paginacion(self):
        """Verifica que la paginación limite los registros (paginate_by=15)."""
        self.client.force_login(self.user1)

        # Crear 15 registros adicionales para superar el límite de 15 por página
        for i in range(15):
            ValidacionSunat.objects.create(
                comprobante=self.cp1,
                estado_sunat='Aceptado',
                codigo_respuesta='1',
                usuario=self.user1
            )

        url = reverse('historial_validaciones')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_paginated'])
        self.assertEqual(len(response.context['validaciones']), 15)

        # Página 2
        response_p2 = self.client.get(url, {'page': 2})
        self.assertEqual(response_p2.status_code, 200)
        self.assertEqual(len(response_p2.context['validaciones']), 3)

    def test_detalle_comprobante_muestra_historial_acumulativo(self):
        """
        Verifica que en el detalle de un comprobante se muestren todas las validaciones
        anteriores sin sobrescribirse, con fecha, estado, código, mensaje y usuario.
        """
        self.client.force_login(self.user1)
        url = reverse('comprobante_detail', kwargs={'pk': self.cp1.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        historial = response.context['historial_validaciones']
        self.assertEqual(len(historial), 2)

        # Verificar presencia de datos requeridos en el HTML renderizado
        contenido = response.content.decode('utf-8')
        self.assertIn('ACEPTADO', contenido)
        self.assertIn('ERROR_CONSULTA', contenido)
        self.assertIn('ERR_CONEXION', contenido)
        self.assertIn('Comprobante validado correctamente.', contenido)
        self.assertIn('operador1', contenido)
