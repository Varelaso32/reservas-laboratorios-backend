"""Carga datos de prueba: usuarios, espacios, tipos de uso y una reserva de ejemplo.

Se puede correr varias veces: no duplica nada.
Uso: docker compose exec api python -m app.utils.datos_prueba
"""
from datetime import datetime, time, timedelta

from sqlalchemy import func, insert, select

from app.core.database import SessionLocal
from app.models.enums import (
    Cargo,
    EstadoReserva,
    EstadoSolicitud,
    Rol,
    RolReserva,
    TipoEspacio,
)
from app.models.modelos import (
    Espacio,
    ReglaAnticipacionRol,
    Reserva,
    Solicitud,
    TipoUso,
    Usuario,
    espacio_aprobador,
    espacio_tipo_uso,
)
from app.utils.fechas import ZONA_COLOMBIA

# Dominio .test: ningún correo de prueba puede llegar a un buzón real
# (nombre, email, rol, cargo, puede autorizar fuera de franja)
USUARIOS = [
    ("Administrador del Sistema", "admin@reservas.test", Rol.ADMIN, Cargo.ADMINISTRADOR_SISTEMA, True),
    ("Coordinador de Laboratorios", "coordinador.labs@reservas.test", Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS, True),
    ("Administrador de Salas", "admin.salas@reservas.test", Rol.APROBADOR, Cargo.ADMINISTRADOR_SALA, False),
    ("Estudiante de Prueba", "estudiante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE, False),
    ("Docente de Prueba", "docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE, False),
    ("Administrativo de Prueba", "administrativo@reservas.test", Rol.SOLICITANTE, Cargo.ADMINISTRATIVO, False),
]

# (nombre, tipo, capacidad, ubicación, activo, aprobador)
ESPACIOS = [
    ("Laboratorio de Redes", TipoEspacio.LABORATORIO, 25, "Bloque A, piso 2", True, "coordinador.labs@reservas.test"),
    ("Laboratorio de Electrónica", TipoEspacio.LABORATORIO, 20, "Bloque A, piso 3", True, "coordinador.labs@reservas.test"),
    ("Laboratorio de Software", TipoEspacio.LABORATORIO, 30, "Bloque B, piso 1", True, "coordinador.labs@reservas.test"),
    ("Sala de Juntas Norte", TipoEspacio.SALA, 12, "Bloque C, piso 4", True, "admin.salas@reservas.test"),
    ("Auditorio Pequeño", TipoEspacio.SALA, 60, "Bloque C, piso 1", True, "admin.salas@reservas.test"),
    ("Sala de Estudio 3", TipoEspacio.SALA, 8, "Biblioteca, piso 2", False, "admin.salas@reservas.test"),
]

# Actividades del catálogo (HU-22)
TIPOS_USO = [
    "Clase",
    "Práctica de laboratorio",
    "Examen",
    "Auditoría",
    "Sustentación",
    "Reunión",
    "Evento institucional",
]

# Actividades que admite cada espacio. Un espacio sin filas no restringe la actividad.
ACTIVIDADES_POR_ESPACIO = {
    "Laboratorio de Redes": ["Clase", "Práctica de laboratorio", "Examen"],
    "Laboratorio de Electrónica": ["Clase", "Práctica de laboratorio", "Examen"],
    "Laboratorio de Software": ["Clase", "Práctica de laboratorio", "Examen"],
    "Sala de Juntas Norte": ["Reunión", "Auditoría", "Sustentación"],
    "Auditorio Pequeño": ["Evento institucional", "Sustentación", "Auditoría"],
}

# Reglas de uso por espacio (HU-21, HU-28, HU-33, HU-34, HU-36).
# (apertura, cierre, días, max_usos_dia, duracion_maxima_min, separacion_min,
#  ocupacion_minima, requiere_responsable, admite_autorizacion_especial)
REGLAS_POR_ESPACIO = {
    "Laboratorio de Redes": (time(7), time(22), "1,2,3,4,5,6", 4, 180, 10, 5, False, False),
    "Laboratorio de Electrónica": (time(7), time(20), "1,2,3,4,5", 3, 120, 15, 4, False, False),
    "Laboratorio de Software": (time(8), time(22), "1,2,3,4,5,6", 4, 240, 0, None, False, False),
    "Sala de Juntas Norte": (time(8), time(18), "1,2,3,4,5", 3, 120, 15, None, True, False),
    "Auditorio Pequeño": (time(8), time(20), "1,2,3,4,5,6", 2, 240, 30, None, True, True),
}

# Anticipación máxima en días por rol de reserva (HU-37)
ANTICIPACION = {
    RolReserva.ESTUDIANTE: 15,
    RolReserva.DOCENTE: 30,
    RolReserva.COORDINADOR: 60,
    RolReserva.DIRECTOR: 90,
}


def _cargar_usuarios(db) -> dict[str, Usuario]:
    usuarios: dict[str, Usuario] = {}
    for nombre, email, rol, cargo, autoriza in USUARIOS:
        u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
        if u is None:
            u = Usuario(
                nombre=nombre,
                email=email,
                clave_hash="PENDIENTE_LOGIN",
                rol=rol,
                cargo=cargo,
                puede_autorizar_especial=autoriza,
            )
            db.add(u)
            db.flush()
        elif autoriza and not u.puede_autorizar_especial:
            u.puede_autorizar_especial = True
        usuarios[email] = u
    return usuarios


def _cargar_tipos_uso(db) -> dict[str, TipoUso]:
    tipos: dict[str, TipoUso] = {}
    for nombre in TIPOS_USO:
        tipo = db.scalar(select(TipoUso).where(TipoUso.nombre == nombre))
        if tipo is None:
            tipo = TipoUso(nombre=nombre)
            db.add(tipo)
            db.flush()
        tipos[nombre] = tipo
    return tipos


def _cargar_espacios(db, usuarios: dict[str, Usuario], tipos: dict[str, TipoUso]) -> dict[str, Espacio]:
    espacios: dict[str, Espacio] = {}
    for nombre, tipo, capacidad, ubicacion, activo, aprobador in ESPACIOS:
        espacio = db.scalar(select(Espacio).where(Espacio.nombre == nombre))
        if espacio is None:
            espacio = Espacio(
                nombre=nombre, tipo=tipo, capacidad=capacidad, ubicacion=ubicacion, activo=activo
            )
            db.add(espacio)
            db.flush()
        espacios[nombre] = espacio

        asignado = db.scalar(
            select(func.count()).select_from(espacio_aprobador).where(
                espacio_aprobador.c.espacio_id == espacio.id,
                espacio_aprobador.c.usuario_id == usuarios[aprobador].id,
            )
        )
        if not asignado:
            db.execute(
                insert(espacio_aprobador).values(
                    espacio_id=espacio.id, usuario_id=usuarios[aprobador].id
                )
            )

        for nombre_tipo in ACTIVIDADES_POR_ESPACIO.get(nombre, []):
            existe = db.scalar(
                select(func.count()).select_from(espacio_tipo_uso).where(
                    espacio_tipo_uso.c.espacio_id == espacio.id,
                    espacio_tipo_uso.c.tipo_uso_id == tipos[nombre_tipo].id,
                )
            )
            if not existe:
                db.execute(
                    insert(espacio_tipo_uso).values(
                        espacio_id=espacio.id, tipo_uso_id=tipos[nombre_tipo].id
                    )
                )

        reglas = REGLAS_POR_ESPACIO.get(nombre)
        if reglas is not None and espacio.hora_apertura is None:
            (
                apertura,
                cierre,
                dias,
                max_usos,
                duracion,
                separacion,
                ocupacion,
                responsable,
                autorizacion,
            ) = reglas
            espacio.hora_apertura = apertura
            espacio.hora_cierre = cierre
            espacio.dias_operacion = dias
            espacio.max_usos_dia = max_usos
            espacio.duracion_maxima_min = duracion
            espacio.separacion_min = separacion
            espacio.ocupacion_minima = ocupacion
            espacio.requiere_responsable = responsable
            espacio.admite_autorizacion_especial = autorizacion

    return espacios


def _cargar_anticipacion(db) -> None:
    for rol, dias in ANTICIPACION.items():
        regla = db.scalar(select(ReglaAnticipacionRol).where(ReglaAnticipacionRol.rol == rol))
        if regla is None:
            db.add(ReglaAnticipacionRol(rol=rol, dias_maximos=dias))


def _cargar_reserva_ejemplo(db, usuarios: dict[str, Usuario], espacios: dict[str, Espacio]) -> datetime:
    # Una reserva activa mañana de 8:00 a 10:00 en el Laboratorio de Redes,
    # para ver en la consulta de disponibilidad que ese espacio sale ocupado.
    manana = datetime.now(ZONA_COLOMBIA).date() + timedelta(days=1)
    inicio = datetime.combine(manana, time(8, 0), ZONA_COLOMBIA)
    fin = datetime.combine(manana, time(10, 0), ZONA_COLOMBIA)
    lab = espacios["Laboratorio de Redes"]
    existe = db.scalar(select(Reserva).where(Reserva.espacio_id == lab.id, Reserva.inicio == inicio))
    if existe is None:
        estudiante = usuarios["estudiante@reservas.test"]
        coordinador = usuarios["coordinador.labs@reservas.test"]
        solicitud = Solicitud(
            solicitante_id=estudiante.id,
            espacio_id=lab.id,
            inicio=inicio,
            fin=fin,
            proposito="Práctica de redes (dato de prueba)",
            asistentes=15,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=coordinador.id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        db.add(
            Reserva(
                solicitud_id=solicitud.id,
                espacio_id=lab.id,
                usuario_id=estudiante.id,
                inicio=inicio,
                fin=fin,
                estado=EstadoReserva.ACTIVA,
            )
        )
    return manana


def cargar() -> None:
    with SessionLocal() as db:
        usuarios = _cargar_usuarios(db)
        tipos = _cargar_tipos_uso(db)
        espacios = _cargar_espacios(db, usuarios, tipos)
        _cargar_anticipacion(db)
        manana = _cargar_reserva_ejemplo(db, usuarios, espacios)
        db.commit()
    print(
        "Datos de prueba cargados. "
        f"Reserva de ejemplo: Laboratorio de Redes, {manana} de 08:00 a 10:00"
    )


if __name__ == "__main__":
    cargar()
