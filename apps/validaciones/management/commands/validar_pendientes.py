"""
Comando de gestión CLI para ejecutar la validación masiva y controlada
de comprobantes pendientes ante el servicio oficial de SUNAT.

Permite procesar lotes sin límites de timeout web, ideal para cron jobs o tareas en segundo plano.
Uso:
  python manage.py validar_pendientes
  python manage.py validar_pendientes --limite 100 --delay 0.2
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from apps.validaciones.services import ValidacionMasivaService


class Command(BaseCommand):
    help = 'Ejecuta la validación masiva controlada de comprobantes pendientes ante SUNAT'

    def add_arguments(self, parser):
        parser.add_argument(
            '--limite',
            type=int,
            default=50,
            help='Cantidad máxima de comprobantes a procesar en esta ejecución (default: 50)'
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.15,
            help='Pausa en segundos entre consultas a SUNAT para respetar tasa de peticiones (default: 0.15)'
        )
        parser.add_argument(
            '--usuario',
            type=str,
            default=None,
            help='Nombre de usuario para el registro de auditoría (default: primer superusuario o sistema)'
        )

    def handle(self, *args, **options):
        limite = options['limite']
        delay = options['delay']
        usuario_str = options['usuario']

        User = get_user_model()
        usuario = None
        if usuario_str:
            usuario = User.objects.filter(username=usuario_str).first()
        if not usuario:
            usuario = User.objects.filter(is_superuser=True).first() or User.objects.first()

        self.stdout.write(self.style.MIGRATE_HEADING(
            f"=== INICIANDO VALIDACIÓN MASIVA SUNAT (Límite: {limite}, Cadencia: {delay}s) ==="
        ))

        service = ValidacionMasivaService(delay_segundos=delay, ip_origen='127.0.0.1')
        resumen = service.procesar_lote(
            usuario=usuario,
            todos_pendientes=True,
            limite=limite,
        )

        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.MIGRATE_HEADING("RESULTADOS DEL PROCESAMIENTO MASIVO:"))
        self.stdout.write("=" * 50)
        self.stdout.write(f"- TOTAL PROCESADOS : {resumen.total_procesados}")
        self.stdout.write(self.style.SUCCESS(f"- ACEPTADOS        : {resumen.aceptados}"))
        self.stdout.write(self.style.WARNING(f"- OBSERVADOS       : {resumen.observados}"))
        self.stdout.write(self.style.ERROR(f"- RECHAZADOS       : {resumen.rechazados}"))
        self.stdout.write(f"- ERROR DE CONSULTA: {resumen.errores_consulta}")
        self.stdout.write("=" * 50)

        if resumen.detalles:
            self.stdout.write("\nDetalle de comprobantes procesados:")
            for d in resumen.detalles:
                estado_style = (
                    self.style.SUCCESS if d['estado'] == 'ACEPTADO' else (
                        self.style.WARNING if d['estado'] == 'OBSERVADO' else (
                            self.style.ERROR if d['estado'] == 'RECHAZADO' else self.style.NOTICE
                        )
                    )
                )
                self.stdout.write(f"  [{estado_style(d['estado'])}] {d['codigo']} - {d['mensaje']}")
