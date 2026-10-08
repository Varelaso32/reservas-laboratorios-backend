"""Gestión de usuarios: crear, registrarse, listar, consultar, actualizar y activar/desactivar."""
import os
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_clave
from app.models.enums import Cargo, EstadoReserva, Rol
from app.models.modelos import Reserva, Usuario
from app.schemas.usuario import RegistroCrear, UsuarioActualizar, UsuarioCrear
from app.utils.fechas import ZONA_COLOMBIA

# Cargos válidos para cada rol (los mismos que usan los datos de prueba)
CARGOS_POR_ROL = {
    Rol.SOLICITANTE: {Cargo.ESTUDIANTE, Cargo.DOCENTE, Cargo.ADMINISTRATIVO},
    Rol.APROBADOR: {Cargo.COORDINADOR_LABORATORIOS, Cargo.ADMINISTRADOR_SALA},
    Rol.ADMIN: {Cargo.ADMINISTRADOR_SISTEMA},
}

# Dominios permitidos en el auto-registro. Se lee de una variable de entorno del
# sistema, no del .env (config.py rechaza variables que no conoce). En producción
# se puede dejar solo ecci.edu.co: REGISTRO_DOMINIOS=ecci.edu.co
DOMINIOS_REGISTRO = {
    d.strip().lower() for d in os.getenv("REGISTRO_DOMINIOS", "ecci.edu.co,reservas.test").split(",") if d.strip()
}

_INDICE_EMAIL = "ux_usuario_email_lower"
_EMAIL_DUPLICADO = "Ya existe un usuario con ese correo"
_NO_ENCONTRADO = "El usuario no existe"


class ErrorUsuario(Exception):
    """Error de negocio con el código HTTP que le corresponde."""

    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _validar_cargo(rol: Rol, cargo: Cargo | None) -> None:
    if cargo is not None and cargo not in CARGOS_POR_ROL[rol]:
        validos = ", ".join(sorted(c.value for c in CARGOS_POR_ROL[rol]))
        raise ErrorUsuario(400, f"El cargo {cargo.value} no corresponde al rol {rol.value}. Cargos válidos: {validos}")


def _email_en_uso(db: Session, email: str, excepto_id: int | None = None) -> bool:
    consulta = select(Usuario.id).where(func.lower(Usuario.email) == email)
    if excepto_id is not None:
        consulta = consulta.where(Usuario.id != excepto_id)
    return db.scalar(consulta) is not None


def _guardar(db: Session) -> None:
    # El SELECT previo no basta: dos peticiones simultáneas pueden pasarlo las dos.
    # El índice único de la BD deja pasar solo una y aquí se convierte en 409.
    try:
        db.flush()
    except IntegrityError as error:
        if _INDICE_EMAIL in str(error.orig):
            raise ErrorUsuario(409, _EMAIL_DUPLICADO)
        raise


def _obtener_para_cambio(db: Session, usuario_id: int) -> tuple[Usuario, int]:
    """Devuelve el usuario bloqueado y cuántos ADMIN activos hay.

    Primero se bloquean las filas de los admins activos (en orden de id) y después
    la del usuario. Siempre en ese orden, para que dos cambios simultáneos no se
    bloqueen entre sí: si dos admins se quitan el rol al mismo tiempo, el segundo
    espera al primero y ya ve su cambio.
    """
    admins = db.scalars(
        select(Usuario.id)
        .where(Usuario.rol == Rol.ADMIN, Usuario.activo.is_(True))
        .order_by(Usuario.id)
        .with_for_update()
    ).all()
    usuario = db.scalar(select(Usuario).where(Usuario.id == usuario_id).with_for_update())
    if usuario is None:
        raise ErrorUsuario(404, _NO_ENCONTRADO)
    return usuario, len(admins)


def _proteger_ultimo_admin(usuario: Usuario, admins_activos: int, rol_nuevo: Rol, activo_nuevo: bool) -> None:
    """Impide dejar el sistema sin ningún ADMIN activo."""
    deja_de_ser_admin = usuario.rol == Rol.ADMIN and usuario.activo and not (rol_nuevo == Rol.ADMIN and activo_nuevo)
    if deja_de_ser_admin and admins_activos <= 1:
        raise ErrorUsuario(400, "No se puede desactivar ni quitar el rol al único ADMIN activo del sistema")


def crear(db: Session, datos: UsuarioCrear) -> Usuario:
    _validar_cargo(datos.rol, datos.cargo)
    if _email_en_uso(db, datos.email):
        raise ErrorUsuario(409, _EMAIL_DUPLICADO)

    usuario = Usuario(
        nombre=datos.nombre,
        email=datos.email,
        clave_hash=hash_clave(datos.clave),
        rol=datos.rol,
        cargo=datos.cargo,
    )
    db.add(usuario)
    _guardar(db)
    db.commit()
    db.refresh(usuario)
    return usuario


def registrar(db: Session, datos: RegistroCrear) -> Usuario:
    """Auto-registro: siempre SOLICITANTE / ESTUDIANTE. Un ADMIN cambia el cargo después si hace falta."""
    dominio = datos.email.split("@")[1]
    if dominio not in DOMINIOS_REGISTRO:
        permitidos = ", ".join(f"@{d}" for d in sorted(DOMINIOS_REGISTRO))
        raise ErrorUsuario(400, f"Solo se pueden registrar correos institucionales ({permitidos})")
    return crear(
        db,
        UsuarioCrear(
            nombre=datos.nombre, email=datos.email, clave=datos.clave,
            rol=Rol.SOLICITANTE, cargo=Cargo.ESTUDIANTE,
        ),
    )


def listar(db: Session, skip: int, limit: int, rol: Rol | None, activo: bool | None) -> dict:
    filtros = []
    if rol is not None:
        filtros.append(Usuario.rol == rol)
    if activo is not None:
        filtros.append(Usuario.activo.is_(activo))

    total = db.scalar(select(func.count()).select_from(Usuario).where(*filtros))
    ahora = datetime.now(ZONA_COLOMBIA)
    inicio_mes = datetime(ahora.year, ahora.month, 1, tzinfo=ZONA_COLOMBIA)
    if ahora.month == 12:
        fin_mes = datetime(ahora.year + 1, 1, 1, tzinfo=ZONA_COLOMBIA)
    else:
        fin_mes = datetime(ahora.year, ahora.month + 1, 1, tzinfo=ZONA_COLOMBIA)

    reservas_mes = (
        select(
            Reserva.usuario_id.label("usuario_id"),
            func.count(Reserva.id).label("reservas_mes"),
        )
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio >= inicio_mes,
            Reserva.inicio < fin_mes,
        )
        .group_by(Reserva.usuario_id)
        .subquery()
    )
    filas = db.execute(
        select(Usuario, func.coalesce(reservas_mes.c.reservas_mes, 0))
        .outerjoin(reservas_mes, reservas_mes.c.usuario_id == Usuario.id)
        .where(*filtros)
        .order_by(Usuario.id)
        .offset(skip)
        .limit(limit)
    ).all()
    items = [
        {
            "id": usuario.id,
            "nombre": usuario.nombre,
            "email": usuario.email,
            "rol": usuario.rol,
            "cargo": usuario.cargo,
            "activo": usuario.activo,
            "creado_en": usuario.creado_en,
            "reservas_mes": reservas,
        }
        for usuario, reservas in filas
    ]
    return {"total": total, "skip": skip, "limit": limit, "items": items}


def obtener(db: Session, usuario_id: int, actual: Usuario) -> Usuario:
    # Un no admin que pide otro id recibe 404, igual que si no existiera:
    # así no se puede averiguar qué ids están registrados.
    if actual.rol != Rol.ADMIN and actual.id != usuario_id:
        raise ErrorUsuario(404, _NO_ENCONTRADO)
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise ErrorUsuario(404, _NO_ENCONTRADO)
    return usuario


def actualizar(db: Session, usuario_id: int, datos: UsuarioActualizar) -> Usuario:
    cambios = datos.model_dump(exclude_unset=True)
    usuario, admins_activos = _obtener_para_cambio(db, usuario_id)

    rol = cambios.get("rol", usuario.rol)
    cargo = cambios.get("cargo", usuario.cargo)
    # Se valida el estado final: cambiar solo el rol también exige que el cargo actual encaje
    _validar_cargo(rol, cargo)
    _proteger_ultimo_admin(usuario, admins_activos, rol, usuario.activo)

    if "email" in cambios and _email_en_uso(db, cambios["email"], excepto_id=usuario.id):
        raise ErrorUsuario(409, _EMAIL_DUPLICADO)

    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    _guardar(db)
    db.commit()
    db.refresh(usuario)
    return usuario


def cambiar_estado(db: Session, usuario_id: int, activo: bool) -> Usuario:
    usuario, admins_activos = _obtener_para_cambio(db, usuario_id)
    _proteger_ultimo_admin(usuario, admins_activos, usuario.rol, activo)

    # Borrado lógico: la fila se conserva porque solicitudes, reservas e historial la referencian
    usuario.activo = activo
    db.commit()
    db.refresh(usuario)
    return usuario
