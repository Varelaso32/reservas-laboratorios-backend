"""Asistencia, no-show, strikes, sanciones y reactivación (HU-12, 17, 38 a 42).

Cubre:
- HU-38: registro de la asistencia dentro de la tolerancia.
- HU-39: advertencia previa y liberación por no-show.
- HU-40: strikes y bloqueo de nuevas solicitudes.
- HU-41: configuración de la política de tolerancia y sanciones.
- HU-42: reporte de sancionados y reactivación.
- HU-12: prioridad de las solicitudes.
- HU-17: motivo de cancelación (se completa en test_reservas).
"""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.enums import (
    AccionTrazabilidad,
    Cargo,
    EstadoAsistencia,
    EstadoReactivacion,
    EstadoReserva,
    EstadoSolicitud,
    Rol,
    TipoEspacio,
    TipoNotificacion,
)
from app.models.modelos import (
    Espacio,
    Notificacion,
    ParametroSancion,
    Reserva,
    Solicitud,
    Strike,
    Trazabilidad,
    espacio_aprobador,
)
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

RESERVAS = "/api/v1/reservas"
SANCIONES = "/api/v1/sanciones"
CONFIG = "/api/v1/configuracion/sanciones"

POLITICA = {
    "tolerancia_minutos": 10,
    "aviso_minutos": 5,
    "minutos_por_strike": 10,
    "max_strikes": 3,
    "acciones": [
        {"nivel": 1, "accion": "ADVERTENCIA"},
        {"nivel": 2, "accion": "ADVERTENCIA"},
        {"nivel": 3, "accion": "BLOQUEO"},
    ],
}


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _crear_espacio(aprobador_id: int | None = None) -> int:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Espacio {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
        )
        db.add(espacio)
        db.flush()
        if aprobador_id is not None:
            db.execute(
                espacio_aprobador.insert().values(
                    espacio_id=espacio.id, usuario_id=aprobador_id
                )
            )
        db.commit()
        return espacio.id


def _crear_reserva(
    usuario,
    inicio: datetime,
    *,
    espacio_id: int | None = None,
    estado: EstadoSolicitud = EstadoSolicitud.APROBADA,
    prioridad: int = 0,
) -> tuple[int, int]:
    """Reserva con su solicitud, directo en la base, para controlar el horario."""
    with SessionLocal() as db:
        espacio_id = espacio_id or _crear_espacio()
        solicitud = Solicitud(
            solicitante_id=usuario.id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=inicio + timedelta(hours=1),
            proposito="Prueba de asistencia",
            asistentes=5,
            estado=estado,
            decidido_por=usuario.id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
            prioridad=prioridad,
        )
        db.add(solicitud)
        db.flush()
        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio_id,
            usuario_id=usuario.id,
            inicio=solicitud.inicio,
            fin=solicitud.fin,
            estado=EstadoReserva.ACTIVA,
        )
        db.add(reserva)
        db.commit()
        return reserva.id, solicitud.id


def _configurar(**cambios: object) -> None:
    with SessionLocal() as db:
        parametros = db.get(ParametroSancion, 1)
        if parametros is None:
            parametros = ParametroSancion(id=1, **POLITICA)
            db.add(parametros)
        for campo, valor in cambios.items():
            setattr(parametros, campo, valor)
        db.commit()


def _reserva(reserva_id: int) -> Reserva:
    with SessionLocal() as db:
        return db.get(Reserva, reserva_id)


def _strikes(usuario_id: int) -> list[Strike]:
    with SessionLocal() as db:
        return list(
            db.scalars(select(Strike).where(Strike.usuario_id == usuario_id)).all()
        )


# --------------------------------------------------------------------------- #
# HU-38: registrar la asistencia
# --------------------------------------------------------------------------- #
def test_registra_asistencia_dentro_de_la_tolerancia(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=2)
    reserva_id, solicitud_id = _crear_reserva(solicitante, inicio)

    respuesta = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado_asistencia"] == "ASISTIO"
    assert cuerpo["inicio_efectivo"] is not None

    reserva = _reserva(reserva_id)
    assert reserva.estado_asistencia == EstadoAsistencia.ASISTIO
    assert reserva.estado == EstadoReserva.ACTIVA
    with SessionLocal() as db:
        acciones = list(
            db.scalars(
                select(Trazabilidad.accion).where(
                    Trazabilidad.solicitud_id == solicitud_id
                )
            ).all()
        )
    assert AccionTrazabilidad.ASISTENCIA_REGISTRADA in acciones


def test_no_registra_asistencia_antes_del_inicio(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(minutes=30)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 409
    assert _reserva(reserva_id).estado_asistencia == EstadoAsistencia.PENDIENTE


def test_registrar_dos_veces_la_asistencia_es_idempotente(client, solicitante):
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=1)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    primera = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )
    segunda = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert segunda.json()["estado_asistencia"] == "ASISTIO"
    with SessionLocal() as db:
        cantidad = len(
            db.scalars(
                select(Trazabilidad.id).where(
                    Trazabilidad.reserva_id == reserva_id,
                    Trazabilidad.accion == AccionTrazabilidad.ASISTENCIA_REGISTRADA,
                )
            ).all()
        )
    assert cantidad == 1


def test_no_puede_registrar_asistencia_en_reserva_ajena(client, solicitante, crear_usuario):
    otro = crear_usuario("otro-titular@reservas.test")
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=1)
    reserva_id, _ = _crear_reserva(otro, inicio)

    respuesta = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 404


# --------------------------------------------------------------------------- #
# HU-39: advertencia y no-show
# --------------------------------------------------------------------------- #
def test_avisa_cuando_la_reserva_inicio_y_no_hay_asistencia(client, solicitante):
    _configurar()
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=6)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    reserva = _reserva(reserva_id)
    assert reserva.advertencia_enviada is True
    assert reserva.estado_asistencia == EstadoAsistencia.PENDIENTE
    with SessionLocal() as db:
        avisos = list(
            db.scalars(
                select(Notificacion.tipo).where(
                    Notificacion.usuario_id == solicitante.id
                )
            ).all()
        )
    assert TipoNotificacion.ADVERTENCIA_NO_ASISTENCIA in avisos


def test_vencida_la_tolerancia_queda_como_no_show_y_genera_strike(client, solicitante):
    _configurar()
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.get(f"{RESERVAS}/mias?incluir_canceladas=true", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    reserva = _reserva(reserva_id)
    assert reserva.estado == EstadoReserva.NO_ASISTIO
    assert reserva.estado_asistencia == EstadoAsistencia.NO_ASISTIO

    strikes = _strikes(solicitante.id)
    assert len(strikes) == 1  # 10 minutos de tolerancia / 10 minutos por strike
    assert strikes[0].reserva_id == reserva_id
    with SessionLocal() as db:
        tipos = list(
            db.scalars(
                select(Notificacion.tipo).where(
                    Notificacion.usuario_id == solicitante.id
                )
            ).all()
        )
    assert TipoNotificacion.NO_SHOW_REGISTRADO in tipos


def test_ya_no_puede_registrar_asistencia_si_vencio_la_tolerancia(client, solicitante):
    _configurar()
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    reserva_id, _ = _crear_reserva(solicitante, inicio)

    respuesta = client.post(
        f"{RESERVAS}/{reserva_id}/asistencia", headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 409
    assert _reserva(reserva_id).estado_asistencia == EstadoAsistencia.NO_ASISTIO


def test_el_no_show_libera_el_espacio(client, solicitante):
    _configurar()
    espacio_id = _crear_espacio()
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio, espacio_id=espacio_id)

    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))

    # El espacio ya no tiene una reserva ACTIVA cruzando ese horario
    with SessionLocal() as db:
        activas = list(
            db.scalars(
                select(Reserva.id).where(
                    Reserva.espacio_id == espacio_id,
                    Reserva.estado == EstadoReserva.ACTIVA,
                )
            ).all()
        )
    assert activas == []


# --------------------------------------------------------------------------- #
# HU-40: strikes y bloqueo
# --------------------------------------------------------------------------- #
def test_al_llegar_al_maximo_de_strikes_bloquea_nuevas_solicitudes(client, solicitante):
    _configurar(max_strikes=1)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)
    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))

    respuesta = client.post(
        "/api/v1/solicitudes/",
        json={
            "espacio_id": 999999,
            "fecha": (datetime.now(ZONA_COLOMBIA) + timedelta(days=3)).date().isoformat(),
            "hora_inicio": "08:00",
            "hora_fin": "09:00",
            "proposito": "Prueba de bloqueo",
            "asistentes": 5,
        },
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 403
    assert "strikes" in respuesta.json()["detail"].lower()


def test_mi_estado_muestra_strikes_y_bloqueo(client, solicitante):
    _configurar(max_strikes=1)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)

    respuesta = client.get(f"{SANCIONES}/mi-estado", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["bloqueado"] is True
    assert cuerpo["strikes_activos"] == 1
    assert cuerpo["max_strikes"] == 1
    assert len(cuerpo["strikes"]) == 1
    assert cuerpo["strikes"][0]["espacio"]


# --------------------------------------------------------------------------- #
# HU-41: configuración de la política
# --------------------------------------------------------------------------- #
def test_admin_consulta_la_politica_de_sanciones(client, admin):
    respuesta = client.get(CONFIG, headers=cabecera(admin))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tolerancia_minutos"] == 10
    assert cuerpo["max_strikes"] == 3


def test_solicitante_no_puede_configurar_sanciones(client, solicitante):
    respuesta = client.patch(CONFIG, json=POLITICA, headers=cabecera(solicitante))

    assert respuesta.status_code == 403


def test_admin_actualiza_la_politica_y_queda_registrada(client, admin):
    datos = {**POLITICA, "tolerancia_minutos": 15, "aviso_minutos": 8, "max_strikes": 2}
    datos["acciones"] = [
        {"nivel": 1, "accion": "ADVERTENCIA"},
        {"nivel": 2, "accion": "BLOQUEO"},
    ]

    respuesta = client.patch(CONFIG, json=datos, headers=cabecera(admin))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["tolerancia_minutos"] == 15
    assert cuerpo["max_strikes"] == 2
    with SessionLocal() as db:
        assert db.get(ParametroSancion, 1).actualizado_por == admin.id


def test_el_aviso_debe_ser_menor_que_la_tolerancia(client, admin):
    datos = {**POLITICA, "tolerancia_minutos": 5, "aviso_minutos": 5}

    respuesta = client.patch(CONFIG, json=datos, headers=cabecera(admin))

    assert respuesta.status_code == 422


def test_no_se_puede_repetir_un_nivel_de_accion(client, admin):
    datos = {**POLITICA, "acciones": [
        {"nivel": 1, "accion": "ADVERTENCIA"},
        {"nivel": 1, "accion": "BLOQUEO"},
    ]}

    respuesta = client.patch(CONFIG, json=datos, headers=cabecera(admin))

    assert respuesta.status_code == 422


# --------------------------------------------------------------------------- #
# HU-42: reporte y reactivación
# --------------------------------------------------------------------------- #
def test_reporte_lista_los_usuarios_sancionados(client, admin, solicitante):
    _configurar(max_strikes=1)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)

    respuesta = client.get(f"{SANCIONES}/reporte", headers=cabecera(admin))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total_bloqueados"] == 1
    assert cuerpo["usuarios"][0]["usuario_id"] == solicitante.id
    assert cuerpo["usuarios"][0]["bloqueado"] is True


def test_solicitante_no_ve_el_reporte(client, solicitante):
    respuesta = client.get(f"{SANCIONES}/reporte", headers=cabecera(solicitante))

    assert respuesta.status_code == 403


def test_reactivacion_aceptada_devuelve_el_acceso(client, admin, solicitante):
    _configurar(max_strikes=1)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)
    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))
    strikes = _strikes(solicitante.id)
    assert len(strikes) == 1

    pedido = client.post(
        f"{SANCIONES}/reactivacion",
        json={
            "justificacion": "No pude asistir por una calamidad familiar",
            "strikes": [
                {"strike_id": strikes[0].id, "justificacion": "Estuve en urgencias"}
            ],
        },
        headers=cabecera(solicitante),
    )

    assert pedido.status_code == 201
    reactivacion_id = pedido.json()["id"]

    decision = client.post(
        f"{SANCIONES}/reactivaciones/{reactivacion_id}/decision",
        json={"aprobar": True, "strikes_anular": [strikes[0].id]},
        headers=cabecera(admin),
    )

    assert decision.status_code == 200
    assert decision.json()["estado"] == EstadoReactivacion.ACEPTADA.value
    assert decision.json()["strikes_anulados"] == 1
    assert _strikes(solicitante.id)[0].anulado is True

    estado = client.get(f"{SANCIONES}/mi-estado", headers=cabecera(solicitante)).json()
    assert estado["bloqueado"] is False
    assert estado["strikes_activos"] == 0


def test_reactivacion_rechazada_exige_motivo(client, admin, solicitante):
    _configurar(max_strikes=1)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)
    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))
    strike = _strikes(solicitante.id)[0]

    pedido = client.post(
        f"{SANCIONES}/reactivacion",
        json={
            "justificacion": "No pude asistir por una calamidad familiar",
            "strikes": [{"strike_id": strike.id, "justificacion": "Estuve en urgencias"}],
        },
        headers=cabecera(solicitante),
    ).json()

    sin_motivo = client.post(
        f"{SANCIONES}/reactivaciones/{pedido['id']}/decision",
        json={"aprobar": False},
        headers=cabecera(admin),
    )
    assert sin_motivo.status_code == 422

    rechazo = client.post(
        f"{SANCIONES}/reactivaciones/{pedido['id']}/decision",
        json={"aprobar": False, "motivo": "La justificación no es suficiente"},
        headers=cabecera(admin),
    )
    assert rechazo.status_code == 200
    assert rechazo.json()["estado"] == EstadoReactivacion.RECHAZADA.value
    assert rechazo.json()["motivo_rechazo"] == "La justificación no es suficiente"

    estado = client.get(f"{SANCIONES}/mi-estado", headers=cabecera(solicitante)).json()
    assert estado["bloqueado"] is True


def test_no_puede_pedir_reactivacion_sin_estar_bloqueado(client, solicitante):
    _configurar()

    respuesta = client.post(
        f"{SANCIONES}/reactivacion",
        json={
            "justificacion": "Quiero volver a reservar desde ya",
            "strikes": [{"strike_id": 1, "justificacion": "Sin strike real"}],
        },
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 409


def test_debe_justificar_todos_los_strikes_activos(client, admin, solicitante):
    _configurar(max_strikes=2)
    inicio = datetime.now(ZONA_COLOMBIA) - timedelta(minutes=20)
    _crear_reserva(solicitante, inicio)
    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))
    _crear_reserva(solicitante, inicio + timedelta(minutes=1))
    client.get(f"{RESERVAS}/mias", headers=cabecera(solicitante))
    strikes = _strikes(solicitante.id)
    assert len(strikes) == 2

    respuesta = client.post(
        f"{SANCIONES}/reactivacion",
        json={
            "justificacion": "No pude asistir a ninguna de las dos reservas",
            "strikes": [
                {"strike_id": strikes[0].id, "justificacion": "Estuve en urgencias"}
            ],
        },
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 422


# --------------------------------------------------------------------------- #
# HU-12: prioridad de las solicitudes
# --------------------------------------------------------------------------- #
def test_la_prioridad_se_ordena_de_mayor_a_menor_en_la_bandeja(
    client, admin, crear_usuario
):
    aprobador = crear_usuario("aprobador-prioridad@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio(aprobador.id)
    estudiante = crear_usuario("prioridad-est@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    coordinador = crear_usuario(
        "prioridad-coord@reservas.test", Rol.SOLICITANTE, Cargo.COORDINADOR_LABORATORIOS
    )
    inicio = datetime.now(ZONA_COLOMBIA) + timedelta(days=2)

    baja_id, _ = _crear_reserva(
        estudiante,
        inicio,
        espacio_id=espacio_id,
        estado=EstadoSolicitud.PENDIENTE,
        prioridad=0,
    )
    alta_id, _ = _crear_reserva(
        coordinador,
        inicio + timedelta(hours=1),
        espacio_id=espacio_id,
        estado=EstadoSolicitud.PENDIENTE,
        prioridad=2,
    )

    respuesta = client.get(
        f"/api/v1/solicitudes/pendientes?espacio_id={espacio_id}",
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    pendientes = respuesta.json()
    assert [p["id"] for p in pendientes] == [alta_id, baja_id]
    assert pendientes[0]["prioridad_etiqueta"] == "ALTA"
    assert pendientes[1]["prioridad_etiqueta"] == "BAJA"
