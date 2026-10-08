"""Pruebas de solicitudes resueltas por espacio."""
from datetime import datetime, time, timedelta
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.enums import EstadoSolicitud, Rol, TipoEspacio
from app.models.modelos import Espacio, Solicitud, espacio_aprobador
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera


URL = "/api/v1/solicitudes/resueltas"


def _crear_historial(espacio_id: int, aprobador_id: int, solicitante_id: int):
    hoy = datetime.now(ZONA_COLOMBIA).date()
    ayer = hoy - timedelta(days=1)
    usos = [
        (EstadoSolicitud.APROBADA, datetime.combine(ayer, time(23, 30), ZONA_COLOMBIA), None),
        (EstadoSolicitud.RECHAZADA, datetime.combine(hoy, time(9), ZONA_COLOMBIA), "No hay disponibilidad"),
        (EstadoSolicitud.PENDIENTE, None, None),
    ]
    with SessionLocal() as db:
        solicitudes = []
        for indice, (estado, fecha_decision, motivo) in enumerate(usos):
            inicio = datetime.combine(hoy + timedelta(days=indice + 1), time(10), ZONA_COLOMBIA)
            solicitud = Solicitud(
                solicitante_id=solicitante_id,
                espacio_id=espacio_id,
                inicio=inicio,
                fin=inicio + timedelta(hours=1),
                proposito="Prueba de historial",
                asistentes=2,
                estado=estado,
                decidido_por=aprobador_id if fecha_decision else None,
                fecha_decision=fecha_decision,
                motivo_rechazo=motivo,
            )
            db.add(solicitud)
            solicitudes.append(solicitud)
        db.commit()
        return [solicitud.id for solicitud in solicitudes]


def _crear_espacio_aprobador(aprobador_id: int) -> int:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"Historial resuelto {uuid4().hex}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
        )
        db.add(espacio)
        db.flush()
        db.execute(
            espacio_aprobador.insert().values(espacio_id=espacio.id, usuario_id=aprobador_id)
        )
        espacio_id = espacio.id
        db.commit()
        return espacio_id


def test_aprobador_lista_solicitudes_resueltas_del_espacio(client, solicitante, crear_usuario):
    aprobador = crear_usuario("aprobador-historial@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    ids = _crear_historial(espacio_id, aprobador.id, solicitante.id)

    respuesta = client.get(f"{URL}?espacio_id={espacio_id}", headers=cabecera(aprobador))

    assert respuesta.status_code == 200
    solicitudes = respuesta.json()
    assert [solicitud["id"] for solicitud in solicitudes] == [ids[1], ids[0]]
    assert [solicitud["estado"] for solicitud in solicitudes] == ["RECHAZADA", "APROBADA"]
    assert solicitudes[0]["motivo_rechazo"] == "No hay disponibilidad"
    assert solicitudes[0]["decidida_por"] == aprobador.nombre
    assert solicitudes[1]["motivo_rechazo"] is None


def test_filtros_de_estado_y_fecha_de_resolucion(client, solicitante, crear_usuario):
    aprobador = crear_usuario("filtro-historial@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    ids = _crear_historial(espacio_id, aprobador.id, solicitante.id)
    hoy = datetime.now(ZONA_COLOMBIA).date().isoformat()

    por_estado = client.get(
        f"{URL}?espacio_id={espacio_id}&estado=APROBADA",
        headers=cabecera(aprobador),
    )
    por_fecha = client.get(
        f"{URL}?espacio_id={espacio_id}&fecha_desde={hoy}&fecha_hasta={hoy}",
        headers=cabecera(aprobador),
    )
    rango_invalido = client.get(
        f"{URL}?espacio_id={espacio_id}&fecha_desde={hoy}&fecha_hasta=2000-01-01",
        headers=cabecera(aprobador),
    )

    assert [solicitud["id"] for solicitud in por_estado.json()] == [ids[0]]
    assert [solicitud["id"] for solicitud in por_fecha.json()] == [ids[1]]
    assert rango_invalido.status_code == 422


def test_no_se_puede_consultar_historial_de_espacio_no_asignado(client, solicitante, crear_usuario):
    aprobador = crear_usuario("otro-aprobador@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    ids = _crear_historial(espacio_id, aprobador.id, solicitante.id)
    otro_aprobador = crear_usuario("sin-asignacion@reservas.test", Rol.APROBADOR)

    respuesta = client.get(f"{URL}?espacio_id={espacio_id}", headers=cabecera(otro_aprobador))

    assert respuesta.status_code == 200
    assert respuesta.json() == []


def test_admin_consulta_historial_de_cualquier_espacio(client, admin, solicitante, crear_usuario):
    aprobador = crear_usuario("aprobador-admin-ve@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    ids = _crear_historial(espacio_id, aprobador.id, solicitante.id)

    respuesta = client.get(f"{URL}?espacio_id={espacio_id}", headers=cabecera(admin))

    assert respuesta.status_code == 200
    assert [solicitud["id"] for solicitud in respuesta.json()] == [ids[1], ids[0]]


def test_admin_no_puede_aprobar_ni_rechazar(client, admin, solicitante, crear_usuario):
    aprobador = crear_usuario("aprobador-admin-no@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    pendiente = _crear_historial(espacio_id, aprobador.id, solicitante.id)[2]

    aprobar = client.post(f"/api/v1/solicitudes/{pendiente}/aprobar", headers=cabecera(admin))
    rechazar = client.post(
        f"/api/v1/solicitudes/{pendiente}/rechazar",
        json={"motivo": "Prueba"},
        headers=cabecera(admin),
    )

    assert aprobar.status_code == 403
    assert rechazar.status_code == 403


def test_solicitante_no_puede_consultar_historial_resuelto(client, solicitante):
    respuesta = client.get(f"{URL}?espacio_id=1", headers=cabecera(solicitante))

    assert respuesta.status_code == 403


def test_admin_consulta_pendientes_de_todos_los_espacios(client, admin, solicitante, crear_usuario):
    aprobador = crear_usuario("aprobador-pendientes@reservas.test", Rol.APROBADOR)
    espacio_id = _crear_espacio_aprobador(aprobador.id)
    pendiente = _crear_historial(espacio_id, aprobador.id, solicitante.id)[2]

    respuesta = client.get(f"/api/v1/solicitudes/pendientes?espacio_id={espacio_id}", headers=cabecera(admin))

    assert respuesta.status_code == 200
    assert [solicitud["id"] for solicitud in respuesta.json()] == [pendiente]


def test_solicitante_no_consulta_pendientes(client, solicitante):
    respuesta = client.get("/api/v1/solicitudes/pendientes", headers=cabecera(solicitante))

    assert respuesta.status_code == 403
