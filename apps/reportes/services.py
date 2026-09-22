import io
from datetime import datetime
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer


class ExportadorExcelService:
    """
    Servicio para exportar los comprobantes a Excel (.xlsx) cumpliendo estrictamente con:
    1. RUC
    2. TIPO
    3. SERIE
    4. NUMERO
    5. FECHA EMISION
    6. MONTO
    7. ESTADO
    8. FECHA VALIDACION
    9. MENSAJE
    10. USUARIO
    """

    COLUMNAS = [
        'RUC',
        'TIPO',
        'SERIE',
        'NUMERO',
        'FECHA EMISION',
        'MONTO',
        'ESTADO',
        'FECHA VALIDACION',
        'MENSAJE',
        'USUARIO'
    ]

    @classmethod
    def generar_excel(cls, comprobantes, titulo="Reporte de Comprobantes SUNAT") -> io.BytesIO:
        wb = Workbook()
        ws = wb.active
        ws.title = "Comprobantes"

        # Estilos corporativos
        header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        border_thin = Side(border_style="thin", color="D3D3D3")
        cell_border = Border(left=border_thin, right=border_thin, top=border_thin, bottom=border_thin)

        # Fila 1: Título institucional
        ws.merge_cells("A1:J1")
        title_cell = ws["A1"]
        title_cell.value = f"{titulo} - Generado el {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        title_cell.font = Font(name="Calibri", size=14, bold=True, color="1F4E79")
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 30

        # Fila 2: Encabezados obligatorios
        ws.row_dimensions[2].height = 25
        for col_idx, col_name in enumerate(cls.COLUMNAS, start=1):
            cell = ws.cell(row=2, column=col_idx, value=col_name)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_align
            cell.border = cell_border

        # Filas de datos
        row_idx = 3
        for cp in comprobantes:
            # Obtener última validación si existe
            ult_val = None
            if hasattr(cp, 'validaciones_list') and cp.validaciones_list:
                ult_val = cp.validaciones_list[0]
            elif hasattr(cp, 'validaciones'):
                ult_val = cp.validaciones.order_by('-fecha_validacion').first()

            fecha_val_str = ult_val.fecha_validacion.strftime('%d/%m/%Y %H:%M:%S') if ult_val else ''
            mensaje_val = ult_val.mensaje if (ult_val and ult_val.mensaje) else ''
            
            # Determinar usuario
            usuario_nombre = 'Sistema'
            if ult_val and ult_val.usuario:
                usuario_nombre = ult_val.usuario.username
            elif cp.usuario_registro:
                usuario_nombre = cp.usuario_registro.username

            valores = [
                cp.ruc_emisor,
                cp.get_tipo_comprobante_display(),
                cp.serie,
                cp.numero,
                cp.fecha_emision.strftime('%d/%m/%Y') if cp.fecha_emision else '',
                float(cp.monto) if cp.monto is not None else 0.0,
                cp.estado,
                fecha_val_str,
                mensaje_val,
                usuario_nombre
            ]

            ws.row_dimensions[row_idx].height = 20
            for col_idx, valor in enumerate(valores, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=valor)
                cell.border = cell_border
                cell.font = Font(name="Calibri", size=10)

                # Formato y alineación según columna
                if col_idx in (1, 3, 4, 5, 7, 8):  # RUC, Serie, Número, Fechas, Estado
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx == 6:  # MONTO
                    cell.alignment = Alignment(horizontal="right", vertical="center")
                    cell.number_format = '#,##0.00'
                else:
                    cell.alignment = Alignment(horizontal="left", vertical="center")

            row_idx += 1

        # Ajuste dinámico de anchos de columna
        anchos_fijos = {
            1: 15,  # RUC
            2: 24,  # TIPO
            3: 10,  # SERIE
            4: 12,  # NUMERO
            5: 14,  # FECHA EMISION
            6: 14,  # MONTO
            7: 16,  # ESTADO
            8: 20,  # FECHA VALIDACION
            9: 35,  # MENSAJE
            10: 16  # USUARIO
        }
        for col_idx, ancho in anchos_fijos.items():
            ws.column_dimensions[get_column_letter(col_idx)].width = ancho

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output


class ExportadorPdfService:
    """
    Servicio para exportar los comprobantes a PDF corporativo mediante ReportLab.
    Configura orientación horizontal (Landscape) y diseño profesional.
    """

    @classmethod
    def generar_pdf(cls, comprobantes, titulo="Reporte de Comprobantes Electrónicos", resumen_filtros="") -> io.BytesIO:
        output = io.BytesIO()
        doc = SimpleDocTemplate(
            output,
            pagesize=landscape(letter),
            leftMargin=20,
            rightMargin=20,
            topMargin=25,
            bottomMargin=25
        )

        styles = getSampleStyleSheet()
        normal_style = styles['Normal']

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=18,
            textColor=colors.HexColor('#1F4E79'),
            fontName='Helvetica-Bold'
        )

        subtitle_style = ParagraphStyle(
            'DocSubtitle',
            parent=normal_style,
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#555555')
        )

        cell_header_style = ParagraphStyle(
            'CellHeader',
            parent=normal_style,
            fontSize=8,
            leading=9,
            textColor=colors.white,
            fontName='Helvetica-Bold',
            alignment=1
        )

        cell_text_style = ParagraphStyle(
            'CellText',
            parent=normal_style,
            fontSize=7,
            leading=8
        )

        cell_center_style = ParagraphStyle(
            'CellCenter',
            parent=normal_style,
            fontSize=7,
            leading=8,
            alignment=1
        )

        cell_right_style = ParagraphStyle(
            'CellRight',
            parent=normal_style,
            fontSize=7,
            leading=8,
            alignment=2
        )

        elements = []

        # Encabezado del Documento
        elements.append(Paragraph("SUNAT VALIDATOR - SISTEMA DE GESTIÓN TRIBUTARIA", title_style))
        elements.append(Paragraph(f"{titulo} | Generado el: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", subtitle_style))
        if resumen_filtros:
            elements.append(Paragraph(f"<b>Criterios de búsqueda:</b> {resumen_filtros}", subtitle_style))
        elements.append(Spacer(1, 10))

        # Encabezados de tabla
        table_data = [[
            Paragraph("<b>RUC</b>", cell_header_style),
            Paragraph("<b>Tipo</b>", cell_header_style),
            Paragraph("<b>Comprobante</b>", cell_header_style),
            Paragraph("<b>F. Emisión</b>", cell_header_style),
            Paragraph("<b>Monto (S/)</b>", cell_header_style),
            Paragraph("<b>Estado</b>", cell_header_style),
            Paragraph("<b>F. Validación</b>", cell_header_style),
            Paragraph("<b>Mensaje SUNAT</b>", cell_header_style),
            Paragraph("<b>Usuario</b>", cell_header_style)
        ]]

        for cp in comprobantes[:1500]:  # Límite seguro para documento PDF
            ult_val = None
            if hasattr(cp, 'validaciones_list') and cp.validaciones_list:
                ult_val = cp.validaciones_list[0]
            elif hasattr(cp, 'validaciones'):
                ult_val = cp.validaciones.order_by('-fecha_validacion').first()

            fecha_val_str = ult_val.fecha_validacion.strftime('%d/%m/%y %H:%M') if ult_val else '—'
            msg_str = (ult_val.mensaje[:75] + '...') if (ult_val and ult_val.mensaje and len(ult_val.mensaje) > 75) else (ult_val.mensaje if ult_val else '—')

            usuario_nombre = 'Sistema'
            if ult_val and ult_val.usuario:
                usuario_nombre = ult_val.usuario.username
            elif cp.usuario_registro:
                usuario_nombre = cp.usuario_registro.username

            table_data.append([
                Paragraph(cp.ruc_emisor, cell_center_style),
                Paragraph(cp.get_tipo_comprobante_display().split(' - ')[-1] if ' - ' in cp.get_tipo_comprobante_display() else cp.get_tipo_comprobante_display(), cell_center_style),
                Paragraph(f"<b>{cp.codigo_completo}</b>", cell_center_style),
                Paragraph(cp.fecha_emision.strftime('%d/%m/%Y') if cp.fecha_emision else '—', cell_center_style),
                Paragraph(f"S/ {cp.monto:.2f}", cell_right_style),
                Paragraph(cp.estado, cell_center_style),
                Paragraph(fecha_val_str, cell_center_style),
                Paragraph(msg_str or '—', cell_text_style),
                Paragraph(usuario_nombre, cell_center_style)
            ])

        # Anchos en puntos (Total ~752 pt para landscape letter con márgenes)
        col_widths = [65, 85, 75, 55, 65, 70, 75, 195, 65]

        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E79')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D3D3D3')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

        elements.append(table)
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(f"Total registros incluidos: {len(table_data) - 1}", subtitle_style))

        doc.build(elements)
        output.seek(0)
        return output
