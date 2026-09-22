import csv
import io
import re
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import openpyxl

from django.db import transaction
from apps.auditoria.models import RegistroAuditoria
from apps.comprobantes.models import Comprobante


class ImportacionService:
    """
    Servicio para procesar, validar e importar masivamente comprobantes electrónicos
    desde archivos Excel (.xlsx) o CSV (.csv).
    """
    COLUMNAS_REQUERIDAS = {'RUC', 'TIPO', 'SERIE', 'NUMERO', 'FECHA', 'MONTO'}

    MAPA_TIPOS = {
        '03': '03', 'BOLETA': '03', 'B': '03',
        '01': '01', 'FACTURA': '01', 'F': '01',
        '07': '07', 'NOTA DE CREDITO': '07', 'NC': '07',
        '08': '08', 'NOTA DE DEBITO': '08', 'ND': '08',
    }

    def __init__(self, lote, ip_address=None):
        self.lote = lote
        self.usuario = lote.usuario
        self.ip_address = ip_address

    def procesar(self):
        """
        Ejecuta el procesamiento del archivo cargado.
        No detiene la importación general ante errores de fila individual.
        """
        self.lote.estado = self.lote.EstadoLote.PROCESANDO
        self.lote.save(update_fields=['estado'])

        nombre = self.lote.nombre_archivo.lower()
        filas = []
        error_general = None

        try:
            if nombre.endswith('.xlsx') or nombre.endswith('.xls'):
                filas, error_general = self._leer_excel()
            elif nombre.endswith('.csv'):
                filas, error_general = self._leer_csv()
            else:
                error_general = "Formato no soportado. Solo se permiten archivos .xlsx y .csv."
        except Exception as e:
            error_general = f"Error al abrir o decodificar el archivo: {str(e)}"

        if error_general:
            self.lote.estado = self.lote.EstadoLote.ERROR
            self.lote.errores_detalle = [{'fila': 0, 'error': error_general}]
            self.lote.save()
            return self.lote

        # Procesar y validar filas
        return self._validar_y_guardar(filas)

    def _leer_excel(self):
        wb = openpyxl.load_workbook(self.lote.archivo.path, data_only=True)
        sheet = wb.active

        raw_rows = list(sheet.iter_rows(values_only=True))
        if not raw_rows:
            return [], "El archivo Excel está completamente vacío."

        # Identificar encabezados (primera fila no vacía)
        headers = None
        start_index = 0
        for idx, row in enumerate(raw_rows):
            if any(cell is not None and str(cell).strip() != '' for cell in row):
                headers = [str(cell).strip().upper() if cell is not None else '' for cell in row]
                start_index = idx + 1
                break

        if not headers:
            return [], "No se encontraron encabezados válidos en el archivo Excel."

        # Verificar columnas obligatorias
        missing = self.COLUMNAS_REQUERIDAS - set(headers)
        if missing:
            return [], f"Faltan columnas requeridas en el encabezado: {', '.join(sorted(missing))}"

        header_indices = {col: headers.index(col) for col in self.COLUMNAS_REQUERIDAS}

        filas = []
        for row_num, row in enumerate(raw_rows[start_index:], start=start_index + 1):
            if not any(cell is not None and str(cell).strip() != '' for cell in row):
                continue  # Fila vacía, ignorar
            
            fila_dict = {}
            for col, idx in header_indices.items():
                val = row[idx] if idx < len(row) else None
                fila_dict[col] = val
            fila_dict['_num_fila'] = row_num
            filas.append(fila_dict)

        return filas, None

    def _leer_csv(self):
        contenido = None
        # Intentar con UTF-8 y fallback a latin-1
        for encoding in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                with open(self.lote.archivo.path, 'r', encoding=encoding) as f:
                    contenido = f.read()
                break
            except UnicodeDecodeError:
                continue

        if not contenido:
            return [], "No se pudo leer el archivo CSV con codificación UTF-8 ni Latin-1."

        # Detectar delimitador (, o ;)
        delimitador = ';' if contenido.count(';') > contenido.count(',') else ','
        reader = csv.reader(io.StringIO(contenido), delimiter=delimitador)
        
        raw_rows = list(reader)
        if not raw_rows:
            return [], "El archivo CSV está vacío."

        headers = None
        start_index = 0
        for idx, row in enumerate(raw_rows):
            if any(cell.strip() != '' for cell in row):
                headers = [cell.strip().upper() for cell in row]
                start_index = idx + 1
                break

        if not headers:
            return [], "No se encontraron encabezados válidos en el archivo CSV."

        missing = self.COLUMNAS_REQUERIDAS - set(headers)
        if missing:
            return [], f"Faltan columnas requeridas en el encabezado: {', '.join(sorted(missing))}"

        header_indices = {col: headers.index(col) for col in self.COLUMNAS_REQUERIDAS}

        filas = []
        for row_num, row in enumerate(raw_rows[start_index:], start=start_index + 1):
            if not any(cell.strip() != '' for cell in row):
                continue
            fila_dict = {}
            for col, idx in header_indices.items():
                val = row[idx] if idx < len(row) else ''
                fila_dict[col] = val
            fila_dict['_num_fila'] = row_num
            filas.append(fila_dict)

        return filas, None

    def _validar_y_guardar(self, filas):
        total_leidos = len(filas)
        comprobantes_a_crear = []
        duplicados = []
        errores = []

        # Cache de comprobantes en el archivo y en BD para detección rápida de duplicados
        claves_en_archivo = set()

        for f in filas:
            num_fila = f['_num_fila']
            ruc_raw = f.get('RUC')
            tipo_raw = f.get('TIPO')
            serie_raw = f.get('SERIE')
            numero_raw = f.get('NUMERO')
            fecha_raw = f.get('FECHA')
            monto_raw = f.get('MONTO')

            # 1. Detectar filas incompletas
            if any(v is None or str(v).strip() == '' for v in (ruc_raw, tipo_raw, serie_raw, numero_raw, fecha_raw, monto_raw)):
                errores.append({
                    'fila': num_fila,
                    'motivo': 'Fila incompleta: uno o más campos requeridos están vacíos.'
                })
                continue

            # 2. Validar RUC
            ruc = str(ruc_raw).strip()
            # En Excel los números pueden venir como float (ej. 20123456789.0)
            if ruc.endswith('.0'):
                ruc = ruc[:-2]
            if not re.match(r'^\d{11}$', ruc):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"RUC inválido '{ruc}': debe tener 11 dígitos numéricos."
                })
                continue
            if not (ruc.startswith('10') or ruc.startswith('20') or ruc.startswith('15') or ruc.startswith('17')):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"RUC inválido '{ruc}': debe iniciar con 10, 20, 15 o 17."
                })
                continue

            # 3. Validar Tipo
            tipo_str = str(tipo_raw).strip().upper()
            if tipo_str.endswith('.0'):
                tipo_str = str(int(float(tipo_str))).zfill(2)
            tipo_normalizado = self.MAPA_TIPOS.get(tipo_str) or (tipo_str.zfill(2) if tipo_str.isdigit() else None)
            if tipo_normalizado not in ('01', '03', '07', '08'):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"Tipo de comprobante inválido '{tipo_raw}'. Se espera 01, 03, 07 u 08."
                })
                continue

            # 4. Validar Serie
            serie = str(serie_raw).strip().upper()
            if not re.match(r'^[B|F|E][A-Z0-9]{3}$', serie):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"Serie inválida '{serie_raw}': debe tener 4 caracteres (ej. B001, F001, EB01)."
                })
                continue

            # 5. Validar Número
            try:
                num_int = int(float(str(numero_raw).strip()))
                if num_int <= 0 or num_int > 99999999:
                    raise ValueError()
            except (ValueError, TypeError):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"Número inválido '{numero_raw}': debe ser un entero positivo (1-99999999)."
                })
                continue

            # 6. Validar Fecha
            fecha_val = None
            if isinstance(fecha_raw, (date, datetime)):
                fecha_val = fecha_raw.date() if isinstance(fecha_raw, datetime) else fecha_raw
            else:
                fecha_str = str(fecha_raw).strip()
                for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
                    try:
                        fecha_val = datetime.strptime(fecha_str, fmt).date()
                        break
                    except ValueError:
                        continue

            if not fecha_val:
                errores.append({
                    'fila': num_fila,
                    'motivo': f"Fecha inválida '{fecha_raw}'. Formato esperado: YYYY-MM-DD o DD/MM/YYYY."
                })
                continue

            if fecha_val > date.today():
                errores.append({
                    'fila': num_fila,
                    'motivo': f"La fecha '{fecha_val}' no puede ser futura."
                })
                continue

            # 7. Validar Monto
            try:
                monto_str = str(monto_raw).strip().replace(',', '')
                monto_val = Decimal(monto_str)
                if monto_val <= 0:
                    raise InvalidOperation()
            except (InvalidOperation, ValueError, TypeError):
                errores.append({
                    'fila': num_fila,
                    'motivo': f"Monto inválido '{monto_raw}': debe ser un número mayor a cero."
                })
                continue

            # 8. Detectar Duplicados
            clave = (ruc, tipo_normalizado, serie, num_int)
            if clave in claves_en_archivo:
                duplicados.append({
                    'fila': num_fila,
                    'comprobante': f"{serie}-{str(num_int).zfill(8)}",
                    'ruc': ruc,
                    'motivo': 'Duplicado dentro del mismo archivo cargado.'
                })
                continue

            claves_en_archivo.add(clave)

            # Comprobar si ya existe en la base de datos
            if Comprobante.objects.filter(
                ruc_emisor=ruc,
                tipo_comprobante=tipo_normalizado,
                serie=serie,
                numero=num_int
            ).exists():
                duplicados.append({
                    'fila': num_fila,
                    'comprobante': f"{serie}-{str(num_int).zfill(8)}",
                    'ruc': ruc,
                    'motivo': 'Ya existe registrado en la base de datos.'
                })
                continue

            # Comprobante válido para ser guardado
            comprobantes_a_crear.append(
                Comprobante(
                    ruc_emisor=ruc,
                    tipo_comprobante=tipo_normalizado,
                    serie=serie,
                    numero=num_int,
                    fecha_emision=fecha_val,
                    monto=monto_val,
                    estado=Comprobante.EstadoComprobante.PENDIENTE,
                    usuario_registro=self.usuario,
                )
            )

        # Inserción atómica en base de datos
        with transaction.atomic():
            if comprobantes_a_crear:
                Comprobante.objects.bulk_create(comprobantes_a_crear)

        importados_correctos = len(comprobantes_a_crear)
        total_duplicados = len(duplicados)
        total_errores = len(errores)

        # Actualizar lote
        self.lote.total_leidos = total_leidos
        self.lote.importados_correctos = importados_correctos
        self.lote.total_duplicados = total_duplicados
        self.lote.total_errores = total_errores
        self.lote.duplicados_detalle = duplicados
        self.lote.errores_detalle = errores

        if importados_correctos > 0 and (total_errores > 0 or total_duplicados > 0):
            self.lote.estado = self.lote.EstadoLote.COMPLETADO
        elif importados_correctos > 0:
            self.lote.estado = self.lote.EstadoLote.COMPLETADO
        elif total_leidos == 0:
            self.lote.estado = self.lote.EstadoLote.ERROR
        else:
            self.lote.estado = self.lote.EstadoLote.ERROR

        self.lote.save()

        # Registro en bitácora de auditoría
        try:
            RegistroAuditoria.objects.create(
                usuario=self.usuario,
                accion='Importación Masiva de Comprobantes',
                objeto_afectado=f"Lote #{self.lote.id} - {self.lote.nombre_archivo}",
                descripcion=(
                    f"Carga procesada: {total_leidos} filas leídas, "
                    f"{importados_correctos} importados, {total_duplicados} duplicados, "
                    f"{total_errores} con error."
                ),
                ip_origen=self.ip_address
            )
        except Exception:
            pass

        return self.lote
