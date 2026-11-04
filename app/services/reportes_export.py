"""Exportación de reportes a CSV y PDF (HU-15, HU-24).

El PDF siempre deja constancia de quién lo generó, con qué rol y a qué hora,
porque es el requisito de auditoría del módulo de reportes.
"""
import csv
import io
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.modelos import Usuario
from app.utils.fechas import ZONA_COLOMBIA

# Tipo de reporte -> (título, columnas). El orden de las columnas manda en CSV y PDF.
REPORTES: dict[str, dict] = {
    "resumen": {
        "titulo": "Resumen semanal",
        "columnas": [
            ("dia", "Día", 26),
            ("fecha", "Fecha", 26),
            ("reservas", "Reservas", 22),
            ("cancelaciones", "Cancelaciones", 26),
            ("no_shows", "No-shows", 22),
            ("tasa_ocupacion", "Ocupación (%)", 26),
        ],
    },
    "ocupacion": {
        "titulo": "Reporte de ocupación",
        "columnas": [
            ("espacio", "Espacio", 50),
            ("tipo", "Tipo", 26),
            ("reservas", "Reservas", 18),
            ("horas_reservadas", "Horas reservadas", 28),
            ("horas_disponibles", "Horas disponibles", 30),
            ("tasa_ocupacion", "Ocupación (%)", 24),
        ],
    },
    "actividad": {
        "titulo": "Actividad por usuario",
        "columnas": [
            ("nombre", "Usuario", 55),
            ("email", "Correo", 70),
            ("rol", "Rol", 30),
            ("reservas", "Reservas", 22),
            ("cancelaciones", "Cancelaciones", 26),
            ("no_shows", "No-shows", 22),
        ],
    },
    "no-shows": {
        "titulo": "No-shows",
        "columnas": [
            ("reserva_id", "Reserva", 22),
            ("fecha", "Fecha", 26),
            ("inicio", "Inicio", 20),
            ("fin", "Fin", 20),
            ("espacio", "Espacio", 62),
            ("usuario", "Usuario", 52),
        ],
    },
    "picos": {
        "titulo": "Picos de demanda",
        "columnas": [
            ("categoria", "Categoría", 40),
            ("franja", "Día / Franja", 60),
            ("reservas", "Reservas", 24),
        ],
    },
    "auditoria": {
        "titulo": "Auditoría del sistema",
        "columnas": [
            ("fecha", "Fecha y hora", 40),
            ("usuario", "Usuario", 38),
            ("origen", "Origen", 28),
            ("accion", "Acción", 28),
            ("entidad", "Entidad", 40),
            ("detalle", "Detalle", 80),
        ],
    },
}

_ROLES = {"ADMIN": "Administrador", "APROBADOR": "Aprobador", "SOLICITANTE": "Solicitante"}


class ErrorExportacion(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _texto(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.astimezone(ZONA_COLOMBIA).strftime("%Y-%m-%d %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


def _periodo(desde: date | None, hasta: date | None) -> str:
    if desde and hasta:
        return f"{desde.strftime('%d/%m/%Y')} – {hasta.strftime('%d/%m/%Y')}"
    return "Histórico completo"


def _filas(tipo: str, datos) -> list[list[str]]:
    columnas = REPORTES[tipo]["columnas"]
    return [
        [_texto(fila.get(clave)) for clave, _, _ in columnas] for fila in datos
    ]


def _cabeceras(tipo: str) -> list[str]:
    return [titulo for _, titulo, _ in REPORTES[tipo]["columnas"]]


def _anchos(tipo: str) -> list[float]:
    return [ancho * mm for _, _, ancho in REPORTES[tipo]["columnas"]]


def generar_csv(
    tipo: str,
    datos,
    usuario: Usuario,
    desde: date | None = None,
    hasta: date | None = None,
    generado: datetime | None = None,
) -> bytes:
    """CSV con metadatos de generación como líneas de comentario."""
    if tipo not in REPORTES:
        raise ErrorExportacion(404, f"El reporte '{tipo}' no existe")
    generado = generado or datetime.now(ZONA_COLOMBIA)
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["# Reporte", REPORTES[tipo]["titulo"]])
    escritor.writerow(["# Generado por", f"{usuario.nombre} ({_ROLES.get(usuario.rol.value, usuario.rol.value)})"])
    escritor.writerow(["# Fecha y hora de generación", generado.strftime("%Y-%m-%d %H:%M:%S")])
    escritor.writerow(["# Periodo", _periodo(desde, hasta)])
    escritor.writerow([])
    escritor.writerow(_cabeceras(tipo))
    for fila in _filas(tipo, datos):
        escritor.writerow(fila)
    # BOM para que Excel en Windows respete los acentos
    return "\ufeff".encode("utf-8") + salida.getvalue().encode("utf-8")


def _pie(canvas, documento, usuario: Usuario, generado: datetime, periodo: str):
    canvas.saveState()
    ancho, _ = documento.pagesize
    canvas.setStrokeColor(colors.black)
    canvas.setLineWidth(0.6)
    canvas.line(15 * mm, 15 * mm, ancho - 15 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#4a4a4a"))
    canvas.drawString(
        15 * mm,
        10 * mm,
        f"Generado por {usuario.nombre} ({_ROLES.get(usuario.rol.value, usuario.rol.value)}) "
        f"el {generado.strftime('%d/%m/%Y %H:%M')} · Periodo: {periodo}",
    )
    canvas.drawRightString(
        ancho - 15 * mm, 10 * mm, f"Página {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def generar_pdf(
    tipo: str,
    datos,
    usuario: Usuario,
    desde: date | None = None,
    hasta: date | None = None,
    generado: datetime | None = None,
) -> bytes:
    """PDF con encabezado institucional, metadatos de generación y paginación."""
    if tipo not in REPORTES:
        raise ErrorExportacion(404, f"El reporte '{tipo}' no existe")
    generado = generado or datetime.now(ZONA_COLOMBIA)
    periodo = _periodo(desde, hasta)
    definicion = REPORTES[tipo]

    buffer = io.BytesIO()
    apaisado = tipo in {"actividad", "auditoria", "no-shows"}
    pagina = landscape(A4) if apaisado else A4
    documento = SimpleDocTemplate(
        buffer,
        pagesize=pagina,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=22 * mm,
        title=definicion["titulo"],
        author=usuario.nombre,
        subject=f"Reporte {definicion['titulo']} · {periodo}",
    )

    estilos = getSampleStyleSheet()
    titulo = ParagraphStyle(
        "TituloReporte",
        parent=estilos["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=0,
        spaceAfter=2,
    )
    subtitulo = ParagraphStyle(
        "SubtituloReporte",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4a4a4a"),
    )
    celda = ParagraphStyle(
        "Celda",
        parent=estilos["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=9.5,
    )
    celdaCabecera = ParagraphStyle(
        "CeldaCabecera",
        parent=celda,
        fontName="Helvetica-Bold",
        textColor=colors.white,
    )

    elementos = [
        Paragraph("ReservaECCI · Plataforma de reservas", subtitulo),
        Spacer(1, 3 * mm),
        Paragraph(definicion["titulo"], titulo),
        Spacer(1, 2 * mm),
        Paragraph(
            f"Generado por: <b>{usuario.nombre}</b> "
            f"({_ROLES.get(usuario.rol.value, usuario.rol.value)})<br/>"
            f"Fecha y hora de generación: {generado.strftime('%d/%m/%Y %H:%M:%S')}<br/>"
            f"Periodo del reporte: {periodo}",
            subtitulo,
        ),
        Spacer(1, 5 * mm),
    ]

    tabla_datos = [
        [Paragraph(texto, celdaCabecera) for texto in _cabeceras(tipo)]
    ]
    for fila in _filas(tipo, datos):
        tabla_datos.append([Paragraph(texto or "—", celda) for texto in fila])

    if len(tabla_datos) == 1:
        elementos.append(
            Paragraph("No hay información registrada para el periodo seleccionado.", subtitulo)
        )
    else:
        tabla = Table(tabla_datos, colWidths=_anchos(tipo), repeatRows=1)
        tabla.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f9ff")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elementos.append(tabla)

    documento.build(
        elementos,
        onFirstPage=lambda lienzo, doc: _pie(lienzo, doc, usuario, generado, periodo),
        onLaterPages=lambda lienzo, doc: _pie(lienzo, doc, usuario, generado, periodo),
    )
    return buffer.getvalue()


def nombre_archivo(tipo: str, extension: str, generado: datetime | None = None) -> str:
    generado = generado or datetime.now(ZONA_COLOMBIA)
    return f"reporte-{tipo}-{generado.strftime('%Y%m%d-%H%M')}.{extension}"
