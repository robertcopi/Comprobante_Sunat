from django.core.management.base import BaseCommand
from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Crea usuarios de prueba para los tres roles: ADMINISTRADOR, SUPERVISOR y TRABAJADOR'

    def handle(self, *args, **options):
        usuarios_data = [
            {
                'username': 'admin_user',
                'email': 'admin@sunatvalidator.pe',
                'password': 'AdminPassword123!',
                'role': User.Role.ADMINISTRADOR,
                'first_name': 'Carlos',
                'last_name': 'Administrador',
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'username': 'supervisor_user',
                'email': 'supervisor@sunatvalidator.pe',
                'password': 'SuperPassword123!',
                'role': User.Role.SUPERVISOR,
                'first_name': 'Mariana',
                'last_name': 'Supervisora',
                'is_staff': False,
                'is_superuser': False,
            },
            {
                'username': 'trabajador_user',
                'email': 'trabajador@sunatvalidator.pe',
                'password': 'TrabajadorPassword123!',
                'role': User.Role.TRABAJADOR,
                'first_name': 'Jorge',
                'last_name': 'Trabajador',
                'is_staff': False,
                'is_superuser': False,
            },
        ]

        self.stdout.write(self.style.NOTICE('Creando usuarios de prueba...'))

        for u in usuarios_data:
            user, created = User.objects.get_or_create(
                username=u['username'],
                defaults={
                    'email': u['email'],
                    'role': u['role'],
                    'first_name': u['first_name'],
                    'last_name': u['last_name'],
                    'is_staff': u['is_staff'],
                    'is_superuser': u['is_superuser'],
                }
            )
            user.set_password(u['password'])
            user.role = u['role']
            user.is_staff = u['is_staff']
            user.is_superuser = u['is_superuser']
            user.save()

            estado = 'creado' if created else 'actualizado'
            self.stdout.write(
                self.style.SUCCESS(
                    f"[OK] Usuario [{u['role']}] {estado}: {u['username']} (password: {u['password']})"
                )
            )

        self.stdout.write(self.style.SUCCESS('\n¡Usuarios listos para pruebas!'))
