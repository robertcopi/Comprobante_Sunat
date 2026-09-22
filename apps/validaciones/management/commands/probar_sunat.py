"""
Comando de gestión para probar la comunicación básica con la API oficial de SUNAT.
Uso:
  python manage.py probar_sunat
  python manage.py probar_sunat --consultar --ruc 20123456789 --tipo 01 --serie F001 --numero 1 --fecha 2026-09-20 --monto 100.00
"""

from django.core.management.base import BaseCommand
from services.sunat import SunatAuthError, SunatClient, SunatConfigError, SunatConnectionError


class Command(BaseCommand):
    help = 'Prueba la conectividad y autenticación oficial con la API de SUNAT'

    def add_arguments(self, parser):
        parser.add_argument(
            '--consultar',
            action='store_true',
            help='Realiza además una consulta individual de prueba de comprobante',
        )
        parser.add_argument('--ruc', type=str, default='20000000001', help='RUC del emisor para la consulta')
        parser.add_argument('--tipo', type=str, default='01', help='Tipo de comprobante (01, 03, etc.)')
        parser.add_argument('--serie', type=str, default='F001', help='Serie del comprobante')
        parser.add_argument('--numero', type=str, default='1', help='Número correlativo')
        parser.add_argument('--fecha', type=str, default='20/09/2026', help='Fecha de emisión (dd/mm/yyyy)')
        parser.add_argument('--monto', type=str, default='100.00', help='Monto total del comprobante')

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING("=== DIAGNÓSTICO DE INTEGRACIÓN OFICIAL SUNAT ==="))

        client = SunatClient()

        # 1. Inspección de credenciales
        ruc_display = client.ruc or "(No configurado)"
        client_id_display = f"{client.client_id[:6]}...{client.client_id[-4:]}" if len(client.client_id) > 10 else ("(No configurado)" if not client.client_id else "***")
        secret_display = "***" if client.client_secret else "(No configurado)"

        self.stdout.write(f"- Modo configurado: {client.modo}")
        self.stdout.write(f"- RUC consultante : {ruc_display}")
        self.stdout.write(f"- Client ID       : {client_id_display}")
        self.stdout.write(f"- Client Secret   : {secret_display}")

        if not client.tiene_credenciales_configuradas():
            self.stdout.write(self.style.WARNING(
                "\n[AVISO] Faltan configurar las variables SUNAT_RUC, SUNAT_CLIENT_ID o SUNAT_CLIENT_SECRET en el archivo .env.\n"
                "Para realizar peticiones reales a SUNAT, genere sus credenciales en SOL (Menú Empresas > Consulta de Validez > Credenciales API) y colóquelas en .env."
            ))
            return

        # 2. Prueba de Autenticación OAuth 2.0
        self.stdout.write("\n1. Probando solicitud de Token OAuth 2.0 a api-seguridad.sunat.gob.pe...")
        try:
            token = client.obtener_token()
            token_masked = f"{token[:12]}...{token[-8:]}" if len(token) > 20 else "***"
            self.stdout.write(self.style.SUCCESS(f"   [OK] Token obtenido exitosamente: {token_masked}"))
        except SunatConfigError as e:
            self.stdout.write(self.style.ERROR(f"   [ERROR CONFIG] {e}"))
            return
        except SunatAuthError as e:
            self.stdout.write(self.style.ERROR(f"   [ERROR AUTENTICACIÓN] {e}"))
            return
        except SunatConnectionError as e:
            self.stdout.write(self.style.ERROR(f"   [ERROR CONEXIÓN] {e}"))
            return

        # 3. Consulta de comprobante si se solicitó
        if options['consultar']:
            self.stdout.write(f"\n2. Probando validación de comprobante {options['tipo']} {options['serie']}-{options['numero']}...")
            try:
                resultado = client.validar_comprobante(
                    num_ruc=options['ruc'],
                    cod_comp=options['tipo'],
                    numero_serie=options['serie'],
                    numero=options['numero'],
                    fecha_emision=options['fecha'],
                    monto=options['monto'],
                )
                self.stdout.write(self.style.SUCCESS(f"   [OK] Respuesta de SUNAT recibida:"))
                self.stdout.write(f"   - Éxito           : {resultado.success}")
                self.stdout.write(f"   - Estado CP       : {resultado.estado_cp} ({resultado.estado_cp_desc})")
                self.stdout.write(f"   - Estado RUC      : {resultado.estado_ruc} ({resultado.estado_ruc_desc})")
                self.stdout.write(f"   - Condición Dom.  : {resultado.cond_domi_ruc} ({resultado.cond_domi_ruc_desc})")
                self.stdout.write(f"   - Estado Sistema  : {resultado.estado_sistema}")
                self.stdout.write(f"   - Mensaje         : {resultado.mensaje}")
                if resultado.observaciones:
                    self.stdout.write(f"   - Observaciones   : {resultado.observaciones}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"   [ERROR CONSULTA] {e}"))
        else:
            self.stdout.write(self.style.SUCCESS("\n[COMPLETADO] La comunicación básica con el servidor de seguridad de SUNAT está lista y operativa."))
            self.stdout.write("Para probar la consulta de un comprobante específico ejecute:")
            self.stdout.write("python manage.py probar_sunat --consultar --ruc <RUC> --tipo <01/03> --serie <SERIE> --numero <NUMERO> --fecha <DD/MM/YYYY> --monto <MONTO>")
