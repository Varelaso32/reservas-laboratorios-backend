"""Reglas de disponibilidad (HU-01). La HU-05 y la aprobación (HU-10) reutilizan esta_disponible."""
from datetime import date, datetime, time

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.enums import EstadoReserva, TipoEspacio
from app.models.modelos import Espacio, Reserva
from app.utils.fechas import ZONA_COLOMBIA


class RangoInvalido(ValueError):
    pass


def construir_rango(fecha: date, hora_inicio: time, hora_fin: time) -> tuple[datetime, datetime]:
    inicio = datetime.combine(fecha, hora_inicio, ZONA_COLOMBIA)
    fin = datetime.combine(fecha, hora_fin, ZONA_COLOMBIA)
    if fin <= inicio:
        raise RangoInvalido("La hora de fin debe ser mayor que la hora de inicio")
    if inicio < datetime.now(ZONA_COLOMBIA):
        raise RangoInvalido("No se puede consultar disponibilidad en fechas u horas pasadas")
    return inicio, fin


def _ocupado(espacio_id, inicio: datetime, fin: datetime):
    # Se cruzan si una empieza antes de que termine la otra. Una reserva que
    # termina a las 10:00 no bloquea otra que empieza a las 10:00.
    return exists().where(
        Reserva.espacio_id == espacio_id,
        Reserva.estado == EstadoReserva.ACTIVA,
        Reserva.inicio < fin,
        Reserva.fin > inicio,
    )


def listar_espacios(db: Session, tipo: TipoEspacio | None = None) -> list[Espacio]:
    consulta = select(Espacio).where(Espacio.activo.is_(True))
    if tipo is not None:
        consulta = consulta.where(Espacio.tipo == tipo)
    return list(db.scalars(consulta.order_by(Espacio.tipo, Espacio.nombre)))


def listar_disponibles(
    db: Session, inicio: datetime, fin: datetime, tipo: TipoEspacio | None = None
) -> list[Espacio]:
    consulta = select(Espacio).where(Espacio.activo.is_(True), ~_ocupado(Espacio.id, inicio, fin))
    if tipo is not None:
        consulta = consulta.where(Espacio.tipo == tipo)
    return list(db.scalars(consulta.order_by(Espacio.tipo, Espacio.nombre)))


def esta_disponible(db: Session, espacio_id: int, inicio: datetime, fin: datetime) -> bool:
    return not db.scalar(select(_ocupado(espacio_id, inicio, fin)))
