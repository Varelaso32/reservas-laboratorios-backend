"""Pruebas del cupo por orden de llegada y la cesión (HU-30, HU-31).

Cubre:
- El cupo se conserva a favor de quien lo pidió primero (HU-30.3).
- Mismo rol o inferior: rechazo automático con motivo (HU-30.4).
- Rol superior: motivo de urgencia obligatorio y espera de cesión (HU-30.5, HU-30.6).
- El titular decide ceder o conservar y ambos reciben notificación (HU-31).
- La decisión queda en la trazabilidad (HU-30.8).
"""
from datetime import datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import (
    AccionTrazabilidad,
    Cargo,
    EstadoReserva,
    EstadoSolicitud,
    Rol,
    TipoEspacio,
    TipoNotificacion,
)
from app.models.modelos import Espacio, Notificacion, Reserva, Solicitud, Trazabilidad
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

URL = "/api/v1/solicitudes/"
NOTIFICACIONES = "/api/v1/notificaciones"


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _crear_espacio(**campos: object) -> int:
    datos = {
        "nombre": f"Espacio {uuid4().hex}",
        "tipo": TipoEspacio.SALA,
        "capacidad": 20,
    }
    datos.update(campos)
    with SessionLocal() as db:
        espacio = Espacio(**datos)
        db.add(espacio)
        db.commit()
        return espacio.id


def _dia(hasta: int = 10) -> str:
    return (datetime.now(ZONA_COLOMBIA).date() + timedelta(days=hasta)).isoformat()


def _cuerpo(
    espacio_id: int, fecha: str, inicio: str, fin: str, **extra: object
) -> dict:
    cuerpo = {
        "espacio_id": espacio_id,
        "fecha": fecha,
        "hora_inicio": inicio,
        "hora_fin": fin,
        "proposito": "Prueba de cesión",
        "asistentes": 5,
    }
    cuerpo.update(extra)
    return cuerpo


def _crear_reserva_directa(espacio_id: int, usuario_id: int, inicio: datetime, fin: datetime) -> int:
    """Deja una reserva ACTIVA a nombre del usuario y devuelve el id de la solicitud."""
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=usuario_id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=fin,
            proposito="Reserva previa",
            asistentes=3,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario_id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        db.add(
            Reserva(
                solicitud_id=solicitud.id,
                espacio_id=espacio_id,
                usuario_id=usuario_id,
                inicio=inicio,
                fin=fin,
                estado=EstadoReserva.ACTIVA,
            )
        )
        db.commit()
        return solicitud.id


def _inicio(fecha: str, hora: str) -> datetime:
    return datetime.combine(
        datetime.fromisoformat(fecha).date(), time.fromisoformat(hora), ZONA_COLOMBIA
    )


def _reserva_activa(espacio_id: int, usuario_id: int) -> Reserva | None:
    with SessionLocal() as db:
        return db.scalar(
            select(Reserva).where(
                Reserva.espacio_id == espacio_id,
                Reserva.usuario_id == usuario_id,
                Reserva.estado == EstadoReserva.ACTIVA,
            )
        )


def _solicitud(solicitud_id: int) -> Solicitud:
    with SessionLocal() as db:
        return db.get(Solicitud, solicitud_id)


def _acciones(solicitud_id: int) -> list[AccionTrazabilidad]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Trazabilidad.accion)
                .where(Trazabilidad.solicitud_id == solicitud_id)
                .order_by(Trazabilidad.id)
            )
        )


def _notificaciones(usuario_id: int) -> list[Notificacion]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(Notificacion)
                .where(Notificacion.usuario_id == usuario_id)
                .order_by(Notificacion.id)
            )
        )


def _pedir_cesion(
    client, usuario, espacio_id: int, fecha: str, inicio: str, fin: str, **extra: object
):
    return client.post(
        URL,
        json=_cuerpo(espacio_id, fecha, inicio, fin, **extra),
        headers=cabecera(usuario),
    )


def _decidir(client, usuario, solicitud_id: int, aprobar: bool, motivo: str | None = None):
    cuerpo = {"aprobar": aprobar}
    if motivo is not None:
        cuerpo["motivo"] = motivo
    return client.post(
        f"{URL}{solicitud_id}/cesion", json=cuerpo, headers=cabecera(usuario)
    )


# --------------------------------------------------------------------------- #
# HU-30: jerarquía y orden de llegada
# --------------------------------------------------------------------------- #
def test_mismo_rol_se_rechaza_automaticamente_con_motivo(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    otro = crear_usuario("otro@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "09:00"), _inicio(fecha, "10:00")
    )

    respuesta = _pedir_cesion(client, otro, espacio_id, fecha, "09:30", "10:30")

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "RECHAZADA"
    assert titular.nombre in cuerpo["motivo_rechazo"]
    assert cuerpo["titular"] == titular.nombre
    assert _acciones(cuerpo["id"]) == [
        AccionTrazabilidad.CREADA,
        AccionTrazabilidad.CONFLICTO_RECHAZADO,
    ]
    # El cupo del titular no se toca
    assert _reserva_activa(espacio_id, titular.id) is not None


def test_rol_inferior_no_puede_pedir_el_cupo(client, crear_usuario):
    titular = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    estudiante = crear_usuario("estudiante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "14:00"), _inicio(fecha, "16:00")
    )

    respuesta = _pedir_cesion(
        client, estudiante, espacio_id, fecha, "14:00", "15:00", motivo_urgencia="Urgente"
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "RECHAZADA"
    assert "jerarquía" in respuesta.json()["motivo_rechazo"]


def test_el_cupo_es_de_quien_lo_pidio_primero_aunque_sea_de_menor_jerarquia(
    client, crear_usuario
):
    # El director pidió primero: quien llega después no puede quitarle el cupo
    director = crear_usuario("director@reservas.test", Rol.SOLICITANTE, Cargo.ADMINISTRADOR_SISTEMA)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, director.id, _inicio(fecha, "08:00"), _inicio(fecha, "09:00")
    )

    respuesta = _pedir_cesion(
        client, docente, espacio_id, fecha, "08:00", "09:00", motivo_urgencia="Clase"
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "RECHAZADA"


def test_rol_superior_sin_motivo_de_urgencia_devuelve_422(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "10:00"), _inicio(fecha, "11:00")
    )

    respuesta = _pedir_cesion(client, docente, espacio_id, fecha, "10:00", "11:00")

    assert respuesta.status_code == 422
    assert "motivo de urgencia" in respuesta.json()["detail"]
    with SessionLocal() as db:
        creadas = list(
            db.scalars(select(Solicitud).where(Solicitud.solicitante_id == docente.id))
        )
    assert creadas == []


def test_rol_superior_con_motivo_queda_en_espera_y_no_quita_el_cupo(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    coordinador = crear_usuario(
        "coordinador@reservas.test", Rol.SOLICITANTE, Cargo.COORDINADOR_LABORATORIOS
    )
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "15:00"), _inicio(fecha, "17:00")
    )

    respuesta = _pedir_cesion(
        client,
        coordinador,
        espacio_id,
        fecha,
        "15:00",
        "16:00",
        motivo_urgencia="Consejo de facultad",
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "EN_ESPERA_CESION"
    assert cuerpo["motivo_urgencia"] == "Consejo de facultad"
    assert cuerpo["titular"] == titular.nombre
    # El titular conserva su reserva (HU-30, criterio 6)
    assert _reserva_activa(espacio_id, titular.id) is not None
    # El titular recibe el aviso con todo lo necesario para decidir (HU-31, criterio 2)
    avisos = _notificaciones(titular.id)
    assert len(avisos) == 1
    assert avisos[0].tipo == TipoNotificacion.CESION_SOLICITADA
    assert "Consejo de facultad" in avisos[0].mensaje
    assert "Coordinador" in avisos[0].mensaje
    assert _acciones(cuerpo["id"]) == [
        AccionTrazabilidad.CREADA,
        AccionTrazabilidad.CESION_SOLICITADA,
    ]


def test_una_reserva_propia_cruzada_sigue_siendo_409(client, crear_usuario):
    # HU-05 se mantiene: no es una cesión, es el mismo usuario chocando consigo mismo
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "09:00"), _inicio(fecha, "10:00")
    )

    respuesta = _pedir_cesion(client, titular, espacio_id, fecha, "09:30", "10:30")

    assert respuesta.status_code == 409
    assert "ocupado" in respuesta.json()["detail"]


def test_el_conflicto_permite_cruzar_el_tope_de_usos_diarios(client, crear_usuario):
    # El uso del titular se reemplaza, no se suma (HU-30)
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio(max_usos_dia=1)
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "09:00"), _inicio(fecha, "10:00")
    )

    respuesta = _pedir_cesion(
        client, docente, espacio_id, fecha, "09:00", "10:00", motivo_urgencia="Examen final"
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "EN_ESPERA_CESION"


def test_fuera_de_franja_manda_la_autorizacion_especial(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio(
        hora_apertura=time(7),
        hora_cierre=time(18),
        admite_autorizacion_especial=True,
    )
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "20:00"), _inicio(fecha, "21:00")
    )

    respuesta = _pedir_cesion(
        client, docente, espacio_id, fecha, "20:00", "21:00", motivo_urgencia="Urgente"
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "PENDIENTE_AUTORIZACION"
    assert _notificaciones(titular.id) == []


# --------------------------------------------------------------------------- #
# HU-31: el titular decide
# --------------------------------------------------------------------------- #
def _preparar_cesion(client, crear_usuario, **campos: object):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio(**campos)
    fecha = _dia()
    _crear_reserva_directa(
        espacio_id, titular.id, _inicio(fecha, "11:00"), _inicio(fecha, "12:00")
    )
    respuesta = _pedir_cesion(
        client, docente, espacio_id, fecha, "11:00", "12:00", motivo_urgencia="Sustentación"
    )
    assert respuesta.status_code == 201
    return titular, docente, espacio_id, fecha, respuesta.json()["id"]


def test_titular_acepta_y_la_reserva_pasa_al_solicitante(client, crear_usuario):
    titular, docente, espacio_id, _, solicitud_id = _preparar_cesion(client, crear_usuario)

    respuesta = _decidir(client, titular, solicitud_id, aprobar=True)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["solicitud"]["estado"] == "APROBADA"
    assert "reserva" in cuerpo["mensaje"].lower()

    assert _reserva_activa(espacio_id, titular.id) is None
    nueva = _reserva_activa(espacio_id, docente.id)
    assert nueva is not None
    assert nueva.solicitud_id == solicitud_id
    assert _solicitud(solicitud_id).estado == EstadoSolicitud.APROBADA

    # Ambos reciben aviso (HU-31, criterio 5)
    tipos_titular = [n.tipo for n in _notificaciones(titular.id)]
    tipos_docente = [n.tipo for n in _notificaciones(docente.id)]
    assert TipoNotificacion.CESION_ACEPTADA in tipos_titular
    assert TipoNotificacion.CESION_CONFIRMADA in tipos_docente
    assert AccionTrazabilidad.CESION_ACEPTADA in _acciones(solicitud_id)


def test_titular_rechaza_sin_motivo_devuelve_422(client, crear_usuario):
    titular, _, _, _, solicitud_id = _preparar_cesion(client, crear_usuario)

    respuesta = _decidir(client, titular, solicitud_id, aprobar=False)

    assert respuesta.status_code == 422
    assert _solicitud(solicitud_id).estado == EstadoSolicitud.EN_ESPERA_CESION


def test_titular_rechaza_con_motivo_y_conserva_su_cupo(client, crear_usuario):
    titular, docente, espacio_id, _, solicitud_id = _preparar_cesion(client, crear_usuario)

    respuesta = _decidir(
        client, titular, solicitud_id, aprobar=False, motivo="El grupo necesita el laboratorio"
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["solicitud"]["estado"] == "RECHAZADA"
    assert _reserva_activa(espacio_id, titular.id) is not None
    assert _reserva_activa(espacio_id, docente.id) is None
    guardada = _solicitud(solicitud_id)
    assert guardada.motivo_rechazo == "El grupo necesita el laboratorio"
    assert guardada.decidido_por == titular.id

    tipos_docente = [n.tipo for n in _notificaciones(docente.id)]
    assert TipoNotificacion.CESION_RECHAZADA in tipos_docente
    assert AccionTrazabilidad.CESION_RECHAZADA in _acciones(solicitud_id)


def test_solo_el_titular_puede_decidir_la_cesion(client, crear_usuario):
    _, docente, _, _, solicitud_id = _preparar_cesion(client, crear_usuario)

    respuesta = _decidir(client, docente, solicitud_id, aprobar=True)

    assert respuesta.status_code == 403
    assert _solicitud(solicitud_id).estado == EstadoSolicitud.EN_ESPERA_CESION


def test_no_se_decide_una_solicitud_que_no_espera_cesion(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=titular.id,
            espacio_id=espacio_id,
            inicio=_inicio(fecha, "13:00"),
            fin=_inicio(fecha, "14:00"),
            proposito="Sin conflicto",
            asistentes=4,
            estado=EstadoSolicitud.PENDIENTE,
            titular_id=titular.id,
        )
        db.add(solicitud)
        db.commit()
        solicitud_id = solicitud.id

    respuesta = _decidir(client, titular, solicitud_id, aprobar=True)

    assert respuesta.status_code == 409
    assert "en espera de cesión" in respuesta.json()["detail"]


def test_una_solicitud_vencida_no_se_puede_ceder(client, crear_usuario):
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio()
    ayer = datetime.now(ZONA_COLOMBIA) - timedelta(days=1)
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=docente.id,
            espacio_id=espacio_id,
            inicio=ayer.replace(hour=10, minute=0),
            fin=ayer.replace(hour=11, minute=0),
            proposito="Ya pasó",
            asistentes=4,
            estado=EstadoSolicitud.EN_ESPERA_CESION,
            motivo_urgencia="Urgente",
            titular_id=titular.id,
        )
        db.add(solicitud)
        db.commit()
        solicitud_id = solicitud.id

    respuesta = _decidir(client, titular, solicitud_id, aprobar=True)

    assert respuesta.status_code == 409
    assert "vencida" in respuesta.json()["detail"]


def test_ceder_el_cupo_de_una_solicitud_pendiente_la_cancela(client, crear_usuario):
    # El cupo del titular puede ser una solicitud aún pendiente, no una reserva
    titular = crear_usuario("titular@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)
    espacio_id = _crear_espacio()
    fecha = _dia()
    with SessionLocal() as db:
        pendiente = Solicitud(
            solicitante_id=titular.id,
            espacio_id=espacio_id,
            inicio=_inicio(fecha, "16:00"),
            fin=_inicio(fecha, "17:00"),
            proposito="Solicitud pendiente del titular",
            asistentes=5,
            estado=EstadoSolicitud.PENDIENTE,
        )
        db.add(pendiente)
        db.commit()
        pendiente_id = pendiente.id

    respuesta = _pedir_cesion(
        client, docente, espacio_id, fecha, "16:00", "17:00", motivo_urgencia="Clase urgente"
    )
    assert respuesta.status_code == 201
    solicitud_id = respuesta.json()["id"]

    decision = _decidir(client, titular, solicitud_id, aprobar=True)

    assert decision.status_code == 200
    assert _solicitud(pendiente_id).estado == EstadoSolicitud.CANCELADA
    assert _reserva_activa(espacio_id, docente.id) is not None


# --------------------------------------------------------------------------- #
# Notificaciones
# --------------------------------------------------------------------------- #
def test_notificaciones_resumen_y_marcar_como_leidas(client, crear_usuario):
    titular, _, _, _, solicitud_id = _preparar_cesion(client, crear_usuario)

    listado = client.get(NOTIFICACIONES + "/", headers=cabecera(titular))
    assert listado.status_code == 200
    avisos = listado.json()
    assert len(avisos) == 1
    assert avisos[0]["solicitud_id"] == solicitud_id
    cesion = avisos[0]["detalle"]
    assert cesion["motivo_urgencia"] == "Sustentación"
    assert cesion["rol_solicitante"] == "DOCENTE"
    assert cesion["solicitante"] == "Usuario docente@reservas.test"

    resumen = client.get(NOTIFICACIONES + "/resumen", headers=cabecera(titular))
    assert resumen.json() == {"no_leidas": 1}

    marcadas = client.post(NOTIFICACIONES + "/leidas", headers=cabecera(titular))
    assert marcadas.json() == {"actualizadas": 1}

    assert client.get(NOTIFICACIONES + "/resumen", headers=cabecera(titular)).json() == {
        "no_leidas": 0
    }


def test_una_notificacion_solo_la_marca_su_dueno(client, crear_usuario):
    titular, docente, _, _, _ = _preparar_cesion(client, crear_usuario)
    aviso_id = _notificaciones(titular.id)[0].id

    respuesta = client.post(
        f"{NOTIFICACIONES}/{aviso_id}/leida", headers=cabecera(docente)
    )

    assert respuesta.status_code == 404
    assert _notificaciones(titular.id)[0].leida is False
