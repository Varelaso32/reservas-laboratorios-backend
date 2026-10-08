"""Gestión administrativa de espacios."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import EstadoReserva, Rol
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario, espacio_aprobador
from app.schemas.espacio import EspacioActualizar, EspacioCrear
from app.services.revision import gestiona_espacio
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


def visibles_para(usuario: Usuario):
    """Consulta de los espacios que gestiona el usuario: el ADMIN todos, el APROBADOR los asignados."""
    consulta = select(Espacio)
    if usuario.rol != Rol.ADMIN:
        consulta = consulta.where(gestiona_espacio(Espacio.id, usuario.id))
    return consulta.order_by(Espacio.tipo, Espacio.nombre)


def listar_admin(db: Session, usuario: Usuario) -> list[Espacio]:
    return list(db.scalars(visibles_para(usuario)))


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
            raise ErrorEspacio(409, _NOMBRE_DUPLICADO)
        raise
    db.commit()
    db.refresh(espacio)
    return espacio


def crear(db: Session, usuario: Usuario, datos: EspacioCrear) -> Espacio:
    """HU-19: registra un espacio nuevo y activo.

    Si lo crea un APROBADOR, queda asignado como su aprobador para que pueda
    gestionarlo. Si lo crea un ADMIN, queda sin aprobadores.
    """
    if _nombre_en_uso(db, datos.nombre):
        raise ErrorEspacio(409, _NOMBRE_DUPLICADO)
    espacio = Espacio(**datos.model_dump(), activo=True)
    db.add(espacio)
    if usuario.rol == Rol.APROBADOR:
        db.flush()
        db.execute(espacio_aprobador.insert().values(espacio_id=espacio.id, usuario_id=usuario.id))
    return _guardar(db, espacio)


def _tomar_gestionable(db: Session, usuario: Usuario, espacio_id: int) -> Espacio:
    """Bloquea el espacio para modificarlo. Un APROBADOR solo puede tomar los asignados;
    si no lo tiene, responde 404 igual que si no existiera."""
    espacio = db.scalar(select(Espacio).where(Espacio.id == espacio_id).with_for_update())
    if espacio is None:
        raise ErrorEspacio(404, _NO_ENCONTRADO)
    if usuario.rol != Rol.ADMIN and not db.scalar(select(gestiona_espacio(espacio.id, usuario.id))):
        raise ErrorEspacio(404, _NO_ENCONTRADO)
    return espacio


def actualizar(db: Session, usuario: Usuario, espacio_id: int, datos: EspacioActualizar) -> Espacio:
    espacio = _tomar_gestionable(db, usuario, espacio_id)

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


def cambiar_estado(db: Session, usuario: Usuario, espacio_id: int, activo: bool) -> Espacio:
    espacio = _tomar_gestionable(db, usuario, espacio_id)
    espacio.activo = activo
    db.commit()
    db.refresh(espacio)
    return espacio
