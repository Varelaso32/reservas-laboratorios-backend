"""Endpoints de reportes y del tablero administrativo (HU-15, HU-24, HU-36)."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import requiere_rol
from app.core.database import get_db
from app.models.enums import Rol
from app.models.modelos import Usuario
from app.schemas.reporte import (
    ActividadUsuarioOut,
    AuditoriaOut,
    DashboardOut,
    NoShowOut,
    OcupacionEspacioOut,
    PicosDemandaOut,
    ResumenDiaOut,
)
from app.services import reportes, reportes_export
from app.utils.fechas import ZONA_COLOMBIA

router = APIRouter()

_SOLO_ADMIN = requiere_rol(Rol.ADMIN)

_PERIODO = Query(None, description="Fecha inicial (YYYY-MM-DD). Por defecto, hace 6 días.")
_PERIODO_FIN = Query(None, description="Fecha final (YYYY-MM-DD). Por defecto, hoy.")


def _ejecutar(funcion, *args, **kwargs: object):
    """Traduce los errores de negocio del servicio a respuestas HTTP."""
    try:
        return funcion(*args, **kwargs)
    except reportes.ErrorReporte as error:
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from None


@router.get(
    "/dashboard",
    response_model=DashboardOut,
    summary="Tablero del administrador",
    description=(
        "**HU-15.** Indicadores del día: reservas activas, solicitudes pendientes, no-shows del mes, "
        "ocupación, usuarios y espacios activos, recursos pendientes, próximas reservas, "
        "serie de los últimos 7 días y los espacios más usados."
    ),
)
def tablero(
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return reportes.dashboard(db)


@router.get(
    "/resumen",
    response_model=list[ResumenDiaOut],
    summary="Resumen semanal",
    description=(
        "**HU-15.** Reservas, cancelaciones, no-shows y tasa de ocupación por día. "
        "Si no se envía periodo, devuelve los últimos 7 días."
    ),
)
def resumen_semanal(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.resumen_semanal, db, desde, hasta)


@router.get(
    "/ocupacion",
    response_model=list[OcupacionEspacioOut],
    summary="Reporte de ocupación",
    description="**HU-15.** Horas reservadas frente a horas disponibles por espacio.",
)
def ocupacion(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    espacio_id: int | None = Query(None, description="Limita el reporte a un espacio."),
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.ocupacion, db, desde, hasta, espacio_id)


@router.get(
    "/actividad",
    response_model=list[ActividadUsuarioOut],
    summary="Actividad por usuario",
    description="**HU-24.** Reservas, cancelaciones y no-shows por usuario.",
)
def actividad(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.actividad_usuarios, db, desde, hasta)


@router.get(
    "/no-shows",
    response_model=list[NoShowOut],
    summary="No-shows",
    description="**HU-24.** Reservas en las que el solicitante no se presentó.",
)
def no_shows(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.no_shows, db, desde, hasta)


@router.get(
    "/picos",
    response_model=PicosDemandaOut,
    summary="Picos de demanda",
    description="**HU-15.** Distribución de reservas activas por día de la semana y por franja horaria.",
)
def picos(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.picos_demanda, db, desde, hasta)


@router.get(
    "/auditoria",
    response_model=list[AuditoriaOut],
    summary="Auditoría del sistema",
    description="**HU-24, HU-36.** Acciones sobre solicitudes y cambios de configuración.",
)
def auditoria(
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    _: Usuario = Depends(_SOLO_ADMIN),
):
    return _ejecutar(reportes.auditoria, db, desde, hasta)


def _datos(tipo: str, db: Session, desde: date | None, hasta: date | None):
    """Datos del reporte pedido, ya normalizados como lista de filas."""
    if tipo == "resumen":
        return _ejecutar(reportes.resumen_semanal, db, desde, hasta)
    if tipo == "ocupacion":
        return _ejecutar(reportes.ocupacion, db, desde, hasta)
    if tipo == "actividad":
        return _ejecutar(reportes.actividad_usuarios, db, desde, hasta)
    if tipo == "no-shows":
        return _ejecutar(reportes.no_shows, db, desde, hasta)
    if tipo == "picos":
        datos = _ejecutar(reportes.picos_demanda, db, desde, hasta)
        return [
            {"categoria": "Día", "franja": fila["dia"], "reservas": fila["reservas"]}
            for fila in datos["por_dia"]
        ] + [
            {"categoria": "Franja", "franja": fila["franja"], "reservas": fila["reservas"]}
            for fila in datos["por_franja"]
        ]
    if tipo == "auditoria":
        return _ejecutar(reportes.auditoria, db, desde, hasta)
    raise HTTPException(status_code=404, detail=f"El reporte '{tipo}' no existe")


@router.get(
    "/{tipo}/export",
    summary="Exportar un reporte",
    description=(
        "**HU-15, HU-24.** Descarga el reporte en `pdf` (por defecto) o `csv`. "
        "El archivo incluye quién lo generó, su rol, la fecha y hora de generación y el periodo."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "text/csv": {},
            },
            "description": "Archivo del reporte",
        },
        404: {"description": "El tipo de reporte no existe"},
    },
)
def exportar(
    tipo: str,
    formato: str = Query("pdf", pattern="^(pdf|csv)$", description="pdf o csv"),
    desde: date | None = _PERIODO,
    hasta: date | None = _PERIODO_FIN,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(_SOLO_ADMIN),
):
    datos = _datos(tipo, db, desde, hasta)
    generado = datetime.now(ZONA_COLOMBIA)
    desde, hasta = _ejecutar(reportes.periodo_efectivo, desde, hasta)
    try:
        if formato == "csv":
            contenido = reportes_export.generar_csv(
                tipo, datos, usuario, desde, hasta, generado
            )
            medio = "text/csv; charset=utf-8"
        else:
            contenido = reportes_export.generar_pdf(
                tipo, datos, usuario, desde, hasta, generado
            )
            medio = "application/pdf"
    except reportes_export.ErrorExportacion as error:
        raise HTTPException(status_code=error.codigo, detail=error.mensaje) from None

    archivo = reportes_export.nombre_archivo(tipo, formato, generado)
    return Response(
        content=contenido,
        media_type=medio,
        headers={"Content-Disposition": f'attachment; filename="{archivo}"'},
    )
