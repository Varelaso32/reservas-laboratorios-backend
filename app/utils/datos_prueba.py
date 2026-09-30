"""Carga datos de prueba: usuarios, espacios y una reserva para probar disponibilidad.

Se puede correr varias veces: no duplica nada.
Uso: docker compose exec api python -m app.utils.datos_prueba

Las claves de los usuarios se definen cuando se implemente el login.
"""
from datetime import datetime, time, timedelta

from sqlalchemy import func, insert, select

from app.core.database import SessionLocal
from app.models.enums import Cargo, EstadoReserva, EstadoSolicitud, Rol, TipoEspacio
from app.models.modelos import Espacio, Reserva, Solicitud, Usuario, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA

# Dominio .test: ningún correo de prueba puede llegar a un buzón real
USUARIOS = [
    ("Administrador del Sistema", "admin@reservas.test", Rol.ADMIN, Cargo.ADMINISTRADOR_SISTEMA),
    ("Coordinador de Laboratorios", "coordinador.labs@reservas.test", Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS),
    ("Administrador de Salas", "admin.salas@reservas.test", Rol.APROBADOR, Cargo.ADMINISTRADOR_SALA),
    ("Estudiante de Prueba", "estudiante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE),
    ("Docente de Prueba", "docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE),
    ("Administrativo de Prueba", "administrativo@reservas.test", Rol.SOLICITANTE, Cargo.ADMINISTRATIVO),
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


def cargar() -> None:
    with SessionLocal() as db:
        usuarios = {}
        for nombre, email, rol, cargo in USUARIOS:
            u = db.scalar(select(Usuario).where(func.lower(Usuario.email) == email))
            if u is None:
                u = Usuario(nombre=nombre, email=email, clave_hash="PENDIENTE_LOGIN", rol=rol, cargo=cargo)
                db.add(u)
                db.flush()
            usuarios[email] = u

        espacios = {}
        for nombre, tipo, capacidad, ubicacion, activo, aprobador in ESPACIOS:
            e = db.scalar(select(Espacio).where(Espacio.nombre == nombre))
            if e is None:
                e = Espacio(nombre=nombre, tipo=tipo, capacidad=capacidad, ubicacion=ubicacion, activo=activo)
                db.add(e)
                db.flush()
            espacios[nombre] = e
            asignado = db.scalar(
                select(func.count()).select_from(espacio_aprobador).where(
                    espacio_aprobador.c.espacio_id == e.id,
                    espacio_aprobador.c.usuario_id == usuarios[aprobador].id,
                )
            )
            if not asignado:
                db.execute(insert(espacio_aprobador).values(espacio_id=e.id, usuario_id=usuarios[aprobador].id))

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
            sol = Solicitud(
                solicitante_id=estudiante.id, espacio_id=lab.id, inicio=inicio, fin=fin,
                proposito="Práctica de redes (dato de prueba)", asistentes=15,
                estado=EstadoSolicitud.APROBADA, decidido_por=coordinador.id,
                fecha_decision=datetime.now(ZONA_COLOMBIA),
            )
            db.add(sol)
            db.flush()
            db.add(Reserva(
                solicitud_id=sol.id, espacio_id=lab.id, usuario_id=estudiante.id,
                inicio=inicio, fin=fin, estado=EstadoReserva.ACTIVA,
            ))

        db.commit()
    print(f"Datos de prueba cargados. Reserva de ejemplo: Laboratorio de Redes, {manana} de 08:00 a 10:00")


if __name__ == "__main__":
    cargar()
