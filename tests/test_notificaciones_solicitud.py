"""Notificaciones del estado de las solicitudes (HU-10, HU-11, HU-35).

La campana debe avisar al solicitante en qué quedó su solicitud y a los
revisores lo que tienen por decidir, sin depender de que recarguen la página.
"""
from datetime import datetime, time, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import Cargo, Rol, TipoEspacio, TipoNotificacion
from app.models.modelos import Espacio, Notificacion, Usuario, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

URL = "/api/v1/solicitudes/"
NOTIFICACIONES = "/api/v1/notificaciones"


def _crear_espacio(**campos) -> int:
    datos = {"nombre": f"Espacio {uuid4().hex}", "tipo": TipoEspacio.SALA, "capacidad": 20}
    datos.update(campos)
    with SessionLocal() as db:
        espacio = Espacio(**datos)
        db.add(espacio)
        db.commit()
        return espacio.id


def _asignar(espacio_id: int, aprobador_id: int) -> None:
    with SessionLocal() as db:
        db.execute(
            espacio_aprobador.insert().values(espacio_id=espacio_id, usuario_id=aprobador_id)
        )
        db.commit()


def _autorizador(crear_usuario, email: str = "autoriza@reservas.test") -> Usuario:
    usuario = crear_usuario(email, Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS)
    with SessionLocal() as db:
        db.get(Usuario, usuario.id).puede_autorizar_especial = True
        db.commit()
    return usuario


def _dia(hasta: int = 10) -> str:
    hoy = datetime.now(ZONA_COLOMBIA).date()
    return (hoy + timedelta(days=hasta)).isoformat()


def _cuerpo(espacio_id: int, inicio: str = "08:00", fin: str = "09:00", **extra) -> dict:
    cuerpo = {
        "espacio_id": espacio_id,
        "fecha": _dia(),
        "hora_inicio": inicio,
        "hora_fin": fin,
        "proposito": "Prueba de notificaciones",
        "asistentes": 5,
    }
    cuerpo.update(extra)
    return cuerpo


def _avisos(usuario: Usuario, tipo: TipoNotificacion | None = None) -> list[Notificacion]:
    with SessionLocal() as db:
        consulta = select(Notificacion).where(Notificacion.usuario_id == usuario.id)
        if tipo is not None:
            consulta = consulta.where(Notificacion.tipo == tipo)
        return list(db.scalars(consulta.order_by(Notificacion.id)))


def _revisores(crear_usuario) -> tuple[Usuario, Usuario]:
    aprobador = crear_usuario(
        "aprobador@reservas.test", Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS
    )
    admin = crear_usuario("admin@reservas.test", Rol.ADMIN, Cargo.ADMINISTRADOR_SISTEMA)
    return aprobador, admin


def test_crear_solicitud_avisa_a_revisores_y_al_solicitante(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio()
    aprobador, admin = _revisores(crear_usuario)
    ajeno = crear_usuario("ajeno@reservas.test", Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS)
    _asignar(espacio_id, aprobador.id)

    creada = client.post(
        URL, json=_cuerpo(espacio_id), headers=cabecera(solicitante)
    ).json()

    for revisor in (aprobador, admin):
        avisos = _avisos(revisor)
        assert [aviso.tipo for aviso in avisos] == [TipoNotificacion.SOLICITUD_PENDIENTE]
        assert avisos[0].solicitud_id == creada["id"]
    # Un aprobador de otros espacios no recibe el aviso
    assert _avisos(ajeno) == []

    propios = _avisos(solicitante)
    assert [aviso.tipo for aviso in propios] == [TipoNotificacion.SOLICITUD_RECIBIDA]
    assert propios[0].solicitud_id == creada["id"]

    # El panel del revisor trae el detalle para decidir sin abrir otra pantalla
    detalle = client.get(NOTIFICACIONES + "/", headers=cabecera(aprobador)).json()[0]["detalle"]
    assert detalle["solicitud_id"] == creada["id"]
    assert detalle["espacio_id"] == espacio_id
    assert detalle["estado"] == "PENDIENTE"
    assert detalle["solicitante"] == solicitante.nombre


def test_aprobar_avisa_al_solicitante_y_retira_el_pendiente_del_revisor(
    client, solicitante, crear_usuario
):
    espacio_id = _crear_espacio()
    aprobador, admin = _revisores(crear_usuario)
    _asignar(espacio_id, aprobador.id)
    creada = client.post(URL, json=_cuerpo(espacio_id), headers=cabecera(solicitante)).json()

    decision = client.post(f"{URL}{creada['id']}/aprobar", headers=cabecera(aprobador))

    assert decision.status_code == 200
    reserva_id = decision.json()["reserva"]["id"]
    aprobada = _avisos(solicitante, TipoNotificacion.SOLICITUD_APROBADA)
    assert len(aprobada) == 1
    assert f"reserva #{reserva_id}" in aprobada[0].mensaje
    # La confirmación de recibida ya no aporta: el resultado la reemplaza
    assert _avisos(solicitante, TipoNotificacion.SOLICITUD_RECIBIDA) == []
    # El aviso accionable ya no tiene sentido: se retira de la campana
    assert _avisos(aprobador, TipoNotificacion.SOLICITUD_PENDIENTE) == []
    assert _avisos(admin, TipoNotificacion.SOLICITUD_PENDIENTE) == []


def test_rechazar_avisa_al_solicitante_con_el_motivo(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio()
    aprobador, _ = _revisores(crear_usuario)
    _asignar(espacio_id, aprobador.id)
    creada = client.post(URL, json=_cuerpo(espacio_id), headers=cabecera(solicitante)).json()

    decision = client.post(
        f"{URL}{creada['id']}/rechazar",
        json={"motivo": "El laboratorio está en mantenimiento"},
        headers=cabecera(aprobador),
    )

    assert decision.status_code == 200
    rechazada = _avisos(solicitante, TipoNotificacion.SOLICITUD_RECHAZADA)
    assert len(rechazada) == 1
    assert "mantenimiento" in rechazada[0].mensaje
    assert _avisos(solicitante, TipoNotificacion.SOLICITUD_RECIBIDA) == []
    assert _avisos(aprobador, TipoNotificacion.SOLICITUD_PENDIENTE) == []

    detalle = next(
        aviso
        for aviso in client.get(NOTIFICACIONES + "/", headers=cabecera(solicitante)).json()
        if aviso["tipo"] == "SOLICITUD_RECHAZADA"
    )["detalle"]
    assert detalle["estado"] == "RECHAZADA"
    assert detalle["motivo_rechazo"] == "El laboratorio está en mantenimiento"


def test_fuera_de_franja_avisa_al_autorizador_y_el_negado_avisa_el_motivo(
    client, solicitante, crear_usuario
):
    espacio_id = _crear_espacio(
        hora_apertura=time(8), hora_cierre=time(12), admite_autorizacion_especial=True
    )
    autorizador = _autorizador(crear_usuario)
    creada = client.post(
        URL, json=_cuerpo(espacio_id, "06:00", "07:00"), headers=cabecera(solicitante)
    ).json()
    assert creada["estado"] == "PENDIENTE_AUTORIZACION"

    assert [aviso.tipo for aviso in _avisos(autorizador)] == [
        TipoNotificacion.SOLICITUD_POR_AUTORIZAR
    ]

    decision = client.post(
        f"{URL}{creada['id']}/autorizacion",
        json={"aprobar": False, "motivo": "Sin vigilancia en ese horario"},
        headers=cabecera(autorizador),
    )

    assert decision.status_code == 200
    assert _avisos(autorizador) == []
    denegada = _avisos(solicitante, TipoNotificacion.AUTORIZACION_DENEGADA)
    assert len(denegada) == 1
    assert "Sin vigilancia en ese horario" in denegada[0].mensaje


def test_autorizar_avisa_al_solicitante_y_a_los_revisores(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio(
        hora_apertura=time(8), hora_cierre=time(12), admite_autorizacion_especial=True
    )
    autorizador = _autorizador(crear_usuario)
    aprobador, admin = _revisores(crear_usuario)
    _asignar(espacio_id, aprobador.id)
    creada = client.post(
        URL, json=_cuerpo(espacio_id, "06:00", "07:00"), headers=cabecera(solicitante)
    ).json()

    decision = client.post(
        f"{URL}{creada['id']}/autorizacion",
        json={"aprobar": True},
        headers=cabecera(autorizador),
    )

    assert decision.status_code == 200
    assert decision.json()["solicitud"]["estado"] == "PENDIENTE"
    assert len(_avisos(solicitante, TipoNotificacion.AUTORIZACION_CONCEDIDA)) == 1
    for revisor in (aprobador, admin):
        assert [aviso.tipo for aviso in _avisos(revisor)] == [
            TipoNotificacion.SOLICITUD_PENDIENTE
        ]
    assert _avisos(autorizador) == []
