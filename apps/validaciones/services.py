"""
Servicio de Validación de Comprobantes ante SUNAT.
Orquesta los 9 pasos requeridos para la validación individual:
1. Obtener datos del comprobante.
2. Validar datos localmente.
3. Consultar servicio oficial de SUNAT.
4. Recibir respuesta.
5. Interpretar respuesta según reglas tributarias.
6. Guardar nueva ValidacionSunat (conservando historial).
7. Actualizar estado actual del comprobante (ACEPTADO, OBSERVADO, RECHAZADO, ERROR_CONSULTA).
8. Registrar usuario, fecha, código y mensaje.
9. Registrar acción en auditoría.
"""

from dataclasses import dataclass, field
import logging
import re
import time
from typing import Any, Dict, List, Optional

from django.db import transaction

from apps.auditoria.models import RegistroAuditoria
from apps.comprobantes.models import Comprobante
from apps.validaciones.models import ValidacionSunat
from services.sunat import (
    SunatAuthError,
    SunatClient,
    SunatConfigError,
    SunatConnectionError,
    SunatError,
)

logger = logging.getLogger('apps.validaciones')


@dataclass
class ResultadoValidacionIndividual:
    """Resultado estructurado para informar a la vista y al usuario."""
    exito: bool
    estado_comprobante: str
    mensaje: str
    codigo_respuesta: str = ''
    estado_sunat_desc: str = ''
    observaciones: list = None
    es_error_tecnico: bool = False
    validacion_id: Optional[int] = None


class ValidacionComprobanteService:
    """
    Servicio de negocio para validar un comprobante individual ante SUNAT.
    """

    def __init__(self, client: Optional[SunatClient] = None, ip_origen: Optional[str] = None):
        self.client = client or SunatClient()
        self.ip_origen = ip_origen

    def validar_datos_locales(self, comprobante: Comprobante) -> Optional[str]:
        """
        Paso 2: Valida los datos del comprobante localmente antes de consultar a SUNAT.
        Retorna mensaje de error si no cumple las reglas básicas, o None si es válido.
        """
        if not comprobante.ruc_emisor or not re.match(r'^\d{11}$', str(comprobante.ruc_emisor).strip()):
            return f"RUC de emisor inválido ({comprobante.ruc_emisor}). Debe contener exactamente 11 dígitos numéricos."

        if not comprobante.tipo_comprobante or comprobante.tipo_comprobante not in ['01', '03', '07', '08']:
            return f"Tipo de comprobante no soportado para validación ({comprobante.tipo_comprobante})."

        if not comprobante.serie or len(comprobante.serie.strip()) != 4:
            return f"Serie inválida ({comprobante.serie}). Debe tener exactamente 4 caracteres alfanuméricos."

        if comprobante.numero is None or comprobante.numero <= 0:
            return f"Número de comprobante inválido ({comprobante.numero}). Debe ser mayor a 0."

        if not comprobante.fecha_emision:
            return "El comprobante no tiene fecha de emisión registrada."

        if comprobante.monto is None or comprobante.monto < 0:
            return "El monto del comprobante no puede ser negativo o nulo."

        return None

    def ejecutar_validacion(self, comprobante_id: int, usuario: Any) -> ResultadoValidacionIndividual:
        """
        Ejecuta el flujo completo de validación individual de un comprobante.
        """
        # Paso 1: Obtener datos del comprobante
        try:
            comprobante = Comprobante.objects.get(pk=comprobante_id)
        except Comprobante.DoesNotExist:
            return ResultadoValidacionIndividual(
                exito=False,
                estado_comprobante='ERROR_CONSULTA',
                mensaje=f"Comprobante con ID {comprobante_id} no existe.",
                es_error_tecnico=True
            )

        # Paso 2: Validar datos localmente
        error_local = self.validar_datos_locales(comprobante)
        if error_local:
            with transaction.atomic():
                # Actualizar comprobante a ERROR_CONSULTA
                comprobante.estado = Comprobante.EstadoComprobante.ERROR_CONSULTA
                comprobante.save(update_fields=['estado'])

                # Paso 6 y 8: Guardar ValidacionSunat
                val = ValidacionSunat.objects.create(
                    comprobante=comprobante,
                    estado_sunat='ERROR_LOCAL',
                    codigo_respuesta='VAL_LOCAL',
                    mensaje=f"Error en validación local: {error_local}",
                    usuario=usuario,
                    respuesta_sunat={'error_local': error_local}
                )

                # Paso 9: Registrar auditoría
                RegistroAuditoria.objects.create(
                    usuario=usuario,
                    accion='Validación Local Fallida',
                    objeto_afectado=f"Comprobante {comprobante.codigo_completo}",
                    descripcion=f"Fallo en validación previa local: {error_local}",
                    ip_origen=self.ip_origen
                )

            return ResultadoValidacionIndividual(
                exito=False,
                estado_comprobante=Comprobante.EstadoComprobante.ERROR_CONSULTA,
                mensaje=f"Error en datos locales: {error_local}",
                codigo_respuesta='VAL_LOCAL',
                estado_sunat_desc='Error de Validación Local',
                validacion_id=val.id,
                es_error_tecnico=True
            )

        # Pasos 3, 4 y 5: Consultar servicio oficial de SUNAT y recibir/interpretar respuesta
        try:
            resultado_sunat = self.client.validar_comprobante(
                num_ruc=comprobante.ruc_emisor,
                cod_comp=comprobante.tipo_comprobante,
                numero_serie=comprobante.serie,
                numero=comprobante.numero,
                fecha_emision=comprobante.fecha_emision,
                monto=comprobante.monto,
            )
        except SunatConnectionError:
            # Error de internet, timeout o caída de servicio de SUNAT -> NO significa RECHAZADO
            msg_error = "No se pudo comunicar con SUNAT debido a timeout o fallo de red. El comprobante pasa a ERROR_CONSULTA."
            return self._registrar_error_tecnico(
                comprobante=comprobante,
                usuario=usuario,
                codigo_error='ERR_CONEXION',
                estado_sunat='ERROR_CONEXION',
                mensaje=msg_error,
                detalle_tecnico="Timeout o error de red al contactar servidor de SUNAT."
            )
        except SunatAuthError as e:
            # Error de credenciales o token OAuth 2.0 -> NO significa RECHAZADO
            msg_error = f"Error de autenticación con SUNAT (OAuth 2.0). Verifique credenciales: {e.message}"
            return self._registrar_error_tecnico(
                comprobante=comprobante,
                usuario=usuario,
                codigo_error='ERR_AUTH',
                estado_sunat='ERROR_AUTENTICACION',
                mensaje=msg_error,
                detalle_tecnico=e.raw_response
            )
        except SunatConfigError as e:
            # Faltan credenciales en .env -> NO significa RECHAZADO
            msg_error = f"Configuración incompleta: {e.message}"
            return self._registrar_error_tecnico(
                comprobante=comprobante,
                usuario=usuario,
                codigo_error='ERR_CONFIG',
                estado_sunat='ERROR_CONFIGURACION',
                mensaje=msg_error,
                detalle_tecnico={'error': str(e)}
            )
        except Exception as e:
            # Error no previsto de ejecución
            logger.exception(f"Error inesperado al validar comprobante {comprobante.id}: {e}")
            msg_error = f"Error inesperado al consultar SUNAT: {str(e)}"
            return self._registrar_error_tecnico(
                comprobante=comprobante,
                usuario=usuario,
                codigo_error='ERR_INESPERADO',
                estado_sunat='ERROR_CONSULTA',
                mensaje=msg_error,
                detalle_tecnico={'error': str(e)}
            )

        # Si el cliente recibió respuesta pero con código de error HTTP (ej. 422 de formato/validación)
        if not resultado_sunat.success:
            return self._registrar_error_tecnico(
                comprobante=comprobante,
                usuario=usuario,
                codigo_error=str(resultado_sunat.http_status or '422'),
                estado_sunat='ERROR_SUNAT_422',
                mensaje=f"SUNAT rechazó la consulta (HTTP {resultado_sunat.http_status}): {resultado_sunat.mensaje}",
                detalle_tecnico=resultado_sunat.raw_response
            )

        # Paso 5, 6, 7, 8 y 9: Procesamiento exitoso de respuesta oficial
        nuevo_estado = resultado_sunat.estado_sistema  # ACEPTADO, OBSERVADO, RECHAZADO

        with transaction.atomic():
            # Paso 7: Actualizar estado actual del comprobante
            comprobante.estado = nuevo_estado
            comprobante.save(update_fields=['estado'])

            # Construir texto descriptivo detallado para la bitácora
            desc_detallada = (
                f"Estado CP: {resultado_sunat.estado_cp_desc} [{resultado_sunat.estado_cp}] | "
                f"RUC Emisor: {resultado_sunat.estado_ruc_desc} [{resultado_sunat.estado_ruc}] | "
                f"Domicilio: {resultado_sunat.cond_domi_ruc_desc} [{resultado_sunat.cond_domi_ruc}]"
            )
            if resultado_sunat.observaciones:
                desc_detallada += f" | Obs: {'; '.join(resultado_sunat.observaciones)}"

            # Paso 6 y 8: Guardar ValidacionSunat (conserva historial 1 a N)
            val = ValidacionSunat.objects.create(
                comprobante=comprobante,
                estado_sunat=f"{resultado_sunat.estado_cp_desc} ({resultado_sunat.estado_sistema})",
                codigo_respuesta=resultado_sunat.estado_cp or '1',
                mensaje=desc_detallada,
                usuario=usuario,
                respuesta_sunat=resultado_sunat.raw_response or {}
            )

            # Paso 9: Registrar la acción en auditoría
            RegistroAuditoria.objects.create(
                usuario=usuario,
                accion=f"Validación SUNAT: {nuevo_estado}",
                objeto_afectado=f"Comprobante {comprobante.codigo_completo}",
                descripcion=(
                    f"Comprobante {comprobante.codigo_completo} validado ante SUNAT. "
                    f"Estado resultante: {nuevo_estado}. {desc_detallada}"
                ),
                ip_origen=self.ip_origen
            )

        return ResultadoValidacionIndividual(
            exito=True,
            estado_comprobante=nuevo_estado,
            mensaje=f"Comprobante validado ante SUNAT: {nuevo_estado}. {resultado_sunat.mensaje}",
            codigo_respuesta=resultado_sunat.estado_cp,
            estado_sunat_desc=resultado_sunat.estado_cp_desc,
            observaciones=resultado_sunat.observaciones,
            validacion_id=val.id,
            es_error_tecnico=False
        )

    def _registrar_error_tecnico(
        self,
        comprobante: Comprobante,
        usuario: Any,
        codigo_error: str,
        estado_sunat: str,
        mensaje: str,
        detalle_tecnico: Any
    ) -> ResultadoValidacionIndividual:
        """
        Registra un fallo de comunicación o configuración sin marcar el comprobante como RECHAZADO.
        Establece el estado en ERROR_CONSULTA.
        """
        with transaction.atomic():
            # Actualizar estado a ERROR_CONSULTA (no RECHAZADO)
            comprobante.estado = Comprobante.EstadoComprobante.ERROR_CONSULTA
            comprobante.save(update_fields=['estado'])

            val = ValidacionSunat.objects.create(
                comprobante=comprobante,
                estado_sunat=estado_sunat,
                codigo_respuesta=codigo_error,
                mensaje=mensaje,
                usuario=usuario,
                respuesta_sunat={'detalle': detalle_tecnico} if isinstance(detalle_tecnico, (dict, list, str)) else {}
            )

            RegistroAuditoria.objects.create(
                usuario=usuario,
                accion='Validación SUNAT Fallida',
                objeto_afectado=f"Comprobante {comprobante.codigo_completo}",
                descripcion=f"Error en consulta SUNAT [{codigo_error}]: {mensaje}",
                ip_origen=self.ip_origen
            )

        return ResultadoValidacionIndividual(
            exito=False,
            estado_comprobante=Comprobante.EstadoComprobante.ERROR_CONSULTA,
            mensaje=mensaje,
            codigo_respuesta=codigo_error,
            estado_sunat_desc=estado_sunat,
            validacion_id=val.id,
            es_error_tecnico=True
        )


@dataclass
class ResumenValidacionMasiva:
    """Resumen estadístico del procesamiento masivo por lotes."""
    total_procesados: int = 0
    aceptados: int = 0
    observados: int = 0
    rechazados: int = 0
    errores_consulta: int = 0
    omitidos_por_aceptados: int = 0
    detalles: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_procesados': self.total_procesados,
            'aceptados': self.aceptados,
            'observados': self.observados,
            'rechazados': self.rechazados,
            'errores_consulta': self.errores_consulta,
            'omitidos_por_aceptados': self.omitidos_por_aceptados,
            'detalles': self.detalles,
        }


class ValidacionMasivaService:
    """
    Servicio para procesamiento controlado por lotes de comprobantes ante SUNAT.

    Principios y restricciones:
    - Control de tasa: Aplica un delay entre peticiones (150ms por defecto) para no saturar SUNAT.
    - Reutilización de conexión: Comparte una sola instancia de SunatClient y sesión/token OAuth 2.0.
    - Continuación ante fallos: Si una consulta falla, continúa con las demás.
    - Error no es rechazo: Ante timeout o error de red, registra ERROR_CONSULTA y nunca RECHAZADO.
    - No reprocesar aceptados: Evita revalidar comprobantes ya aceptados, salvo orden explícita.
    - Trazabilidad y auditoría: Registra cada comprobante y una entrada consolidada de auditoría.
    """

    def __init__(
        self,
        client: Optional[SunatClient] = None,
        ip_origen: Optional[str] = None,
        delay_segundos: float = 0.15
    ):
        self.client = client or SunatClient()
        self.ip_origen = ip_origen
        self.delay_segundos = delay_segundos
        self.validador_individual = ValidacionComprobanteService(client=self.client, ip_origen=self.ip_origen)

    def procesar_lote(
        self,
        usuario: Any,
        comprobantes_ids: Optional[List[int]] = None,
        todos_pendientes: bool = False,
        limite: int = 50,
        revalidar_aceptados: bool = False,
    ) -> ResumenValidacionMasiva:
        """
        Ejecuta la validación masiva sobre los comprobantes seleccionados o todos los pendientes.
        """
        resumen = ResumenValidacionMasiva()

        # Determinar el conjunto de comprobantes a procesar
        if todos_pendientes:
            qs = Comprobante.objects.filter(
                estado__in=[Comprobante.EstadoComprobante.PENDIENTE, Comprobante.EstadoComprobante.ERROR_CONSULTA]
            ).order_by('fecha_emision', 'id')
        elif comprobantes_ids:
            # Si se especificaron IDs particulares
            todos_seleccionados = Comprobante.objects.filter(id__in=comprobantes_ids)
            if not revalidar_aceptados:
                # Contar cuántos ya estaban aceptados y omitirlos
                aceptados_omitidos = todos_seleccionados.filter(estado=Comprobante.EstadoComprobante.ACEPTADO).count()
                resumen.omitidos_por_aceptados = aceptados_omitidos
                qs = todos_seleccionados.exclude(estado=Comprobante.EstadoComprobante.ACEPTADO).order_by('fecha_emision', 'id')
            else:
                qs = todos_seleccionados.order_by('fecha_emision', 'id')
        else:
            return resumen

        comprobantes_a_procesar = list(qs[:limite])
        total_items = len(comprobantes_a_procesar)

        logger.info(f"Iniciando validación masiva controlada de {total_items} comprobante(s) por el usuario {usuario.username}...")

        for idx, cp in enumerate(comprobantes_a_procesar, start=1):
            try:
                # Ejecutar validación usando el servicio individual (orquesta los 9 pasos)
                resultado = self.validador_individual.ejecutar_validacion(
                    comprobante_id=cp.id,
                    usuario=usuario
                )

                resumen.total_procesados += 1
                if resultado.estado_comprobante == Comprobante.EstadoComprobante.ACEPTADO:
                    resumen.aceptados += 1
                elif resultado.estado_comprobante == Comprobante.EstadoComprobante.OBSERVADO:
                    resumen.observados += 1
                elif resultado.estado_comprobante == Comprobante.EstadoComprobante.RECHAZADO:
                    resumen.rechazados += 1
                else:
                    # ERROR_CONSULTA
                    resumen.errores_consulta += 1

                resumen.detalles.append({
                    'id': cp.id,
                    'codigo': cp.codigo_completo,
                    'tipo': cp.get_tipo_comprobante_display(),
                    'estado': resultado.estado_comprobante,
                    'mensaje': resultado.mensaje,
                    'exito': resultado.exito,
                })

            except Exception as e:
                # Robustez extrema: capturar cualquier excepción imprevista y continuar con los demás
                logger.error(f"Error imprevisto en validación masiva para comprobante {cp.id}: {e}")
                resumen.total_procesados += 1
                resumen.errores_consulta += 1
                resumen.detalles.append({
                    'id': cp.id,
                    'codigo': cp.codigo_completo,
                    'tipo': cp.get_tipo_comprobante_display(),
                    'estado': Comprobante.EstadoComprobante.ERROR_CONSULTA,
                    'mensaje': f"Falla inesperada en procesamiento masivo: {str(e)}",
                    'exito': False,
                })

            # Control de tasa (pacing): pausa breve entre peticiones para respetar restricciones de SUNAT
            if idx < total_items and self.delay_segundos > 0:
                time.sleep(self.delay_segundos)

        # Registro consolidado en la bitácora de auditoría
        if resumen.total_procesados > 0:
            try:
                RegistroAuditoria.objects.create(
                    usuario=usuario,
                    accion='Validación Masiva SUNAT',
                    objeto_afectado=f"Lote de {resumen.total_procesados} comprobante(s)",
                    descripcion=(
                        f"Procesamiento masivo finalizado. Total: {resumen.total_procesados} | "
                        f"Aceptados: {resumen.aceptados} | Observados: {resumen.observados} | "
                        f"Rechazados: {resumen.rechazados} | Error Consulta: {resumen.errores_consulta}"
                        + (f" | Ya aceptados omitidos: {resumen.omitidos_por_aceptados}" if resumen.omitidos_por_aceptados > 0 else "")
                    ),
                    ip_origen=self.ip_origen
                )
            except Exception as e:
                logger.warning(f"No se pudo registrar auditoría de lote masivo: {e}")

        logger.info(
            f"Validación masiva finalizada. Total: {resumen.total_procesados}, "
            f"Aceptados: {resumen.aceptados}, Observados: {resumen.observados}, "
            f"Rechazados: {resumen.rechazados}, Errores: {resumen.errores_consulta}"
        )

        return resumen
