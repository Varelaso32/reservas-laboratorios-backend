"""Pruebas de los reportes y del tablero del administrador."""
from datetime import date, datetime, time
from uuid import uuid4

from app.core.database import SessionLocal
from app.models.enums import (
    EstadoReserva,
    EstadoSolicitud,
    TipoEspacio,
)
from app.models.modelos import Espacio, Reserva, Solicitud
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

BASE = "/api/v1/reportes"
HOY = datetime.now(ZONA_COLOMBIA).date()


def _crear_espacio(nombre: str, activo: bool = True) -> Espacio:
    with SessionLocal() as db:
        espacio = Espacio(
            nombre=f"{nombre} {uuid4().hex[:6]}",
            tipo=TipoEspacio.LABORATORIO,
            capacidad=20,
            ubicacion="Bloque A",
            activo=activo,
        )
        db.add(espacio)
        db.flush()
        espacio_id = espacio.id
        db.commit()
        return db.get(Espacio, espacio_id)


def _crear_reserva(
    espacio_id: int,
    usuario_id: int,
    inicio: datetime,
    fin: datetime,
    estado: EstadoReserva = EstadoReserva.ACTIVA,
) -> Reserva:
    with SessionLocal() as db:
        solicitud = Solicitud(
            solicitante_id=usuario_id,
            espacio_id=espacio_id,
            inicio=inicio,
            fin=fin,
            proposito="Prueba de reportes",
            asistentes=2,
            estado=EstadoSolicitud.APROBADA,
            decidido_por=usuario_id,
            fecha_decision=datetime.now(ZONA_COLOMBIA),
        )
        db.add(solicitud)
        db.flush()
        reserva = Reserva(
            solicitud_id=solicitud.id,
            espacio_id=espacio_id,
            usuario_id=usuario_id,
            inicio=inicio,
            fin=fin,
            estado=estado,
        )
        db.add(reserva)
        db.flush()
        reserva_id = reserva.id
        db.commit()
        return db.get(Reserva, reserva_id)


def _a_las(fecha: date, hora: int, minutos: int = 0) -> datetime:
    return datetime.combine(fecha, time(hora, minutos), ZONA_COLOMBIA)


def test_dashboard_devuelve_indicadores_del_dia(client, admin, solicitante):
    espacio = _crear_espacio("Dashboard")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 9), _a_las(HOY, 11))

    respuesta = client.get(f"{BASE}/dashboard", headers=cabecera(admin))

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["reservas_hoy"] == 1
    assert datos["espacios_activos"] >= 1
    assert datos["usuarios_activos"] >= 2
    assert len(datos["serie_semanal"]) == 7
    assert datos["serie_semanal"][-1]["fecha"] == HOY.isoformat()


def test_resumen_semanal_cuenta_cancelaciones_y_no_shows(client, admin, solicitante):
    espacio = _crear_espacio("Resumen")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 8), _a_las(HOY, 10))
    _crear_reserva(
        espacio.id, solicitante.id, _a_las(HOY, 11), _a_las(HOY, 12), EstadoReserva.CANCELADA
    )
    _crear_reserva(
        espacio.id, solicitante.id, _a_las(HOY, 13), _a_las(HOY, 14), EstadoReserva.NO_ASISTIO
    )

    respuesta = client.get(
        f"{BASE}/resumen",
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    fila = respuesta.json()[0]
    assert fila["fecha"] == HOY.isoformat()
    assert fila["reservas"] == 3
    assert fila["cancelaciones"] == 1
    assert fila["no_shows"] == 1
    assert fila["tasa_ocupacion"] > 0


def test_ocupacion_calcula_horas_y_excluye_canceladas(client, admin, solicitante):
    espacio = _crear_espacio("Ocupacion")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 8), _a_las(HOY, 10))
    _crear_reserva(
        espacio.id, solicitante.id, _a_las(HOY, 10), _a_las(HOY, 12), EstadoReserva.CANCELADA
    )

    respuesta = client.get(
        f"{BASE}/ocupacion",
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat(), "espacio_id": espacio.id},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    fila = respuesta.json()[0]
    assert fila["espacio_id"] == espacio.id
    assert fila["reservas"] == 1
    assert fila["horas_reservadas"] == 2.0
    assert fila["horas_disponibles"] == 15.0
    assert fila["tasa_ocupacion"] > 0


def test_actividad_por_usuario_agrupa_por_solicitante(client, admin, solicitante):
    espacio = _crear_espacio("Actividad")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 8), _a_las(HOY, 9))
    _crear_reserva(
        espacio.id, solicitante.id, _a_las(HOY, 9), _a_las(HOY, 10), EstadoReserva.CANCELADA
    )

    respuesta = client.get(
        f"{BASE}/actividad",
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    fila = next(f for f in respuesta.json() if f["usuario_id"] == solicitante.id)
    assert fila["reservas"] == 2
    assert fila["cancelaciones"] == 1
    assert fila["rol"] == "SOLICITANTE"


def test_no_shows_lista_solo_inasistencias(client, admin, solicitante):
    espacio = _crear_espacio("NoShow")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 8), _a_las(HOY, 9))
    inasistencia = _crear_reserva(
        espacio.id, solicitante.id, _a_las(HOY, 10), _a_las(HOY, 11), EstadoReserva.NO_ASISTIO
    )

    respuesta = client.get(
        f"{BASE}/no-shows",
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    assert [fila["reserva_id"] for fila in respuesta.json()] == [inasistencia.id]


def test_picos_de_demanda_devuelve_dias_y_franjas(client, admin, solicitante):
    espacio = _crear_espacio("Picos")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 9), _a_las(HOY, 10))

    respuesta = client.get(
        f"{BASE}/picos",
        params={"desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert len(datos["por_dia"]) == 7
    assert sum(fila["reservas"] for fila in datos["por_dia"]) == 1
    franja = next(f for f in datos["por_franja"] if f["franja"] == "09:00 – 11:00")
    assert franja["reservas"] == 1


def test_periodo_invalido_responde_422(client, admin):
    respuesta = client.get(
        f"{BASE}/resumen",
        params={"desde": "2026-05-10", "hasta": "2026-05-01"},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 422
    assert "posterior" in respuesta.json()["detail"]


def test_espacio_inexistente_en_ocupacion_responde_404(client, admin):
    respuesta = client.get(
        f"{BASE}/ocupacion",
        params={"espacio_id": 999999},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 404


def test_exportacion_csv_incluye_metadatos_de_generacion(client, admin, solicitante):
    espacio = _crear_espacio("Csv")
    _crear_reserva(espacio.id, solicitante.id, _a_las(HOY, 8), _a_las(HOY, 9))

    respuesta = client.get(
        f"{BASE}/resumen/export",
        params={"formato": "csv", "desde": HOY.isoformat(), "hasta": HOY.isoformat()},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert "attachment" in respuesta.headers["content-disposition"]
    assert ".csv" in respuesta.headers["content-disposition"]
    texto = respuesta.content.decode("utf-8-sig")
    assert "# Reporte;Resumen semanal" in texto
    assert f"# Generado por;{admin.nombre} (Administrador)" in texto
    assert "# Fecha y hora de generación;" in texto
    assert HOY.strftime("%d/%m/%Y") in texto


def test_exportacion_pdf_incluye_metadatos_y_es_un_pdf_valido(client, admin):
    respuesta = client.get(
        f"{BASE}/ocupacion/export",
        params={"formato": "pdf"},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content.startswith(b"%PDF")
    assert b"%%EOF" in respuesta.content[-1024:]
    assert ".pdf" in respuesta.headers["content-disposition"]


def test_exportacion_de_tipo_desconocido_responde_404(client, admin):
    respuesta = client.get(
        f"{BASE}/inventado/export", params={"formato": "csv"}, headers=cabecera(admin)
    )

    assert respuesta.status_code == 404


def test_solicitante_no_puede_ver_reportes(client, solicitante):
    assert client.get(f"{BASE}/dashboard", headers=cabecera(solicitante)).status_code == 403
    assert client.get(f"{BASE}/resumen", headers=cabecera(solicitante)).status_code == 403
    assert (
        client.get(f"{BASE}/resumen/export", headers=cabecera(solicitante)).status_code == 403
    )


def test_sin_token_responde_401(client):
    assert client.get(f"{BASE}/dashboard").status_code == 401
