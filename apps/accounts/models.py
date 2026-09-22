from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Modelo de usuario personalizado con roles empresariales para el sistema SUNAT Validator.
    """
    class Role(models.TextChoices):
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'
        SUPERVISOR = 'SUPERVISOR', 'Supervisor'
        TRABAJADOR = 'TRABAJADOR', 'Trabajador'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.TRABAJADOR,
        verbose_name='Rol en el Sistema'
    )
    dni = models.CharField(max_length=8, blank=True, null=True, verbose_name='DNI')
    telefono = models.CharField(max_length=15, blank=True, null=True, verbose_name='Teléfono')

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'
        ordering = ['username']

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def is_administrador(self):
        return self.role == self.Role.ADMINISTRADOR or self.is_superuser

    @property
    def is_supervisor(self):
        return self.role == self.Role.SUPERVISOR

    @property
    def is_trabajador(self):
        return self.role == self.Role.TRABAJADOR

    @property
    def puede_consultar_reportes(self):
        return self.is_administrador or self.is_supervisor

    @property
    def puede_registrar_comprobantes(self):
        return self.is_administrador or self.is_trabajador

    @property
    def puede_importar(self):
        return self.is_administrador or self.is_trabajador

    @property
    def puede_validar(self):
        return self.is_administrador or self.is_trabajador

    @property
    def puede_ver_auditoria(self):
        return self.is_administrador
