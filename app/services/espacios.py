"""Gestión administrativa de espacios."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import EstadoReserva
from app.models.modelos import Espacio, Reserva, Solicitud
from app.schemas.espacio import EspacioActualizar, EspacioCrear
from app.utils.fechas import ZONA_COLOMBIA

_NOMBRE_DUPLICADO = "Ya existe un espacio con ese nombre"
_NO_ENCONTRADO = "El espacio no existe"
_INDICE_NOMBRE = "uq_espacio_nombre"


class ErrorEspacio(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def listar_admin(db: Session) -> list[Espacio]:
    return list(db.scalars(select(Espacio).order_by(Espacio.tipo, Espacio.nombre)))


def _nombre_en_uso(db: Session, nombre: str, excluir_id: int | None = None) -> bool:
    consulta = select(Espacio.id).where(Espacio.nombre == nombre)
    if excluir_id is not None:
        consulta = consulta.where(Espacio.id != excluir_id)
    return db.scalar(consulta) is not None


def _guardar(db: Session, espacio: Espacio) -> Espacio:
    # El índice único cubre el caso de dos peticiones simultáneas con el mismo nombre
    try:
        db.flush()
    except IntegrityError as error:
        if _INDICE_NOMBRE in str(error.orig):
            raise ErrorEspacio(409, _NOMBRE_DUPLICADO) from error
        raise
    db.commit()
    db.refresh(espacio)
    return espacio


def crear(db: Session, datos: EspacioCrear) -> Espacio:
    """HU-19: registra un espacio nuevo, activo y sin aprobadores asignados."""
    if _nombre_en_uso(db, datos.nombre):
        raise ErrorEspacio(409, _NOMBRE_DUPLICADO)
    espacio = Espacio(**datos.model_dump(), activo=True)
    db.add(espacio)
    return _guardar(db, espacio)


def actualizar(db: Session, espacio_id: int, datos: EspacioActualizar) -> Espacio:
    espacio = db.scalar(select(Espacio).where(Espacio.id == espacio_id).with_for_update())
    if espacio is None:
        raise ErrorEspacio(404, _NO_ENCONTRADO)

    cambios = datos.model_dump(exclude_unset=True)
    if "nombre" in cambios and _nombre_en_uso(db, cambios["nombre"], espacio.id):
        raise ErrorEspacio(409, _NOMBRE_DUPLICADO)

    if "capacidad" in cambios and cambios["capacidad"] < espacio.capacidad:
        reserva_excedida = db.scalar(
            select(Reserva.id)
            .join(Solicitud, Solicitud.id == Reserva.solicitud_id)
            .where(
                Reserva.espacio_id == espacio.id,
                Reserva.estado == EstadoReserva.ACTIVA,
                Reserva.inicio > datetime.now(ZONA_COLOMBIA),
                Solicitud.asistentes > cambios["capacidad"],
            )
            .limit(1)
        )
        if reserva_excedida is not None:
            raise ErrorEspacio(
                409,
                "No se puede reducir la capacidad: hay una reserva futura con más asistentes que la nueva capacidad",
            )

    for campo, valor in cambios.items():
        setattr(espacio, campo, valor)
    return _guardar(db, espacio)


def cambiar_estado(db: Session, espacio_id: int, activo: bool) -> Espacio:
    espacio = db.scalar(select(Espacio).where(Espacio.id == espacio_id).with_for_update())
    if espacio is None:
        raise ErrorEspacio(404, _NO_ENCONTRADO)
    espacio.activo = activo
    db.commit()
    db.refresh(espacio)
    return espacio
