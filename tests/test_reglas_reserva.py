"""Pruebas de las reglas de reserva configurables por espacio (épicas 6 y 9).

Cubre HU-21, HU-22, HU-28, HU-29, HU-32, HU-33, HU-34, HU-35, HU-36 y HU-37.
"""
from datetime import datetime, time, timedelta
from uuid import uuid4

import pytest

from app.core.database import SessionLocal
from app.models.enums import Cargo, EstadoSolicitud, Rol, RolReserva, TipoEspacio
from app.models.modelos import Espacio, ReglaAnticipacionRol, Solicitud, TipoUso
from app.utils.fechas import ZONA_COLOMBIA
from tests.conftest import cabecera

URL = "/api/v1/solicitudes/"
CONFIG = "/api/v1/configuracion"


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #
def _crear_espacio(**campos) -> int:
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


def _crear_tipo_uso(nombre: str | None = None) -> int:
    with SessionLocal() as db:
        tipo = TipoUso(nombre=nombre or f"Actividad {uuid4().hex}")
        db.add(tipo)
        db.commit()
        return tipo.id


def _asociar_tipo(espacio_id: int, tipo_id: int) -> None:
    from app.models.modelos import espacio_tipo_uso

    with SessionLocal() as db:
        db.execute(
            espacio_tipo_uso.insert().values(espacio_id=espacio_id, tipo_uso_id=tipo_id)
        )
        db.commit()


def _dia(hasta: int = 10) -> str:
    """Fecha futura que no cae en domingo (la operación institucional es todos los días)."""
    hoy = datetime.now(ZONA_COLOMBIA).date()
    return (hoy + timedelta(days=hasta)).isoformat()


def _cuerpo(espacio_id: int, fecha: str, inicio: str, fin: str, **extra) -> dict:
    cuerpo = {
        "espacio_id": espacio_id,
        "fecha": fecha,
        "hora_inicio": inicio,
        "hora_fin": fin,
        "proposito": "Prueba de reglas",
        "asistentes": 5,
    }
    cuerpo.update(extra)
    return cuerpo


def _crear_reserva_directa(espacio_id: int, usuario_id: int, inicio: datetime, fin: datetime):
    from app.models.enums import EstadoReserva
    from app.models.modelos import Reserva

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


# --------------------------------------------------------------------------- #
# HU-28: capacidad y ocupación mínima
# --------------------------------------------------------------------------- #
def test_asistentes_por_encima_de_la_capacidad_se_rechazan(client, solicitante):
    espacio_id = _crear_espacio(capacidad=10)

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", asistentes=11), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "10" in respuesta.json()["detail"]


def test_asistentes_iguales_a_la_capacidad_son_validos(client, solicitante):
    espacio_id = _crear_espacio(capacidad=10)

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", asistentes=10), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_ocupacion_minima_rechaza_y_permite_el_limite(client, solicitante):
    espacio_id = _crear_espacio(capacidad=30, ocupacion_minima=10)

    pocos = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", asistentes=9), headers=cabecera(solicitante)
    )
    justos = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "11:00", "12:00", asistentes=10), headers=cabecera(solicitante)
    )

    assert pocos.status_code == 422
    assert "10" in pocos.json()["detail"]
    assert justos.status_code == 201


def test_sin_ocupacion_minima_no_se_exige_cantidad_minima(client, solicitante):
    espacio_id = _crear_espacio(capacidad=30)

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", asistentes=1), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


# --------------------------------------------------------------------------- #
# HU-29: compatibilidad entre espacio y actividad
# --------------------------------------------------------------------------- #
def test_actividad_no_configurada_se_rechaza_e_informa_las_permitidas(client, solicitante):
    espacio_id = _crear_espacio()
    permitida = _crear_tipo_uso("Clase")
    otra = _crear_tipo_uso("Examen")
    _asociar_tipo(espacio_id, permitida)

    respuesta = client.post(
        URL,
        json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", tipo_uso_id=otra),
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 422
    assert "Clase" in respuesta.json()["detail"]


def test_sin_actividad_indicada_se_rechaza_si_el_espacio_tiene_actividades(client, solicitante):
    espacio_id = _crear_espacio()
    _asociar_tipo(espacio_id, _crear_tipo_uso("Auditoría"))

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "Auditoría" in respuesta.json()["detail"]


def test_actividad_permitida_se_registra_y_se_devuelve(client, solicitante):
    espacio_id = _crear_espacio()
    tipo_id = _crear_tipo_uso("Clase de redes")
    _asociar_tipo(espacio_id, tipo_id)

    respuesta = client.post(
        URL,
        json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", tipo_uso_id=tipo_id),
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["tipo_uso"] == "Clase de redes"


def test_espacio_sin_actividades_no_bloquea_la_solicitud(client, solicitante):
    espacio_id = _crear_espacio()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["tipo_uso"] is None


# --------------------------------------------------------------------------- #
# HU-32: anticipación máxima y responsable
# --------------------------------------------------------------------------- #
def test_anticipacion_del_rol_limita_la_fecha(client, solicitante):
    espacio_id = _crear_espacio()
    with SessionLocal() as db:
        db.add(ReglaAnticipacionRol(rol=RolReserva.ESTUDIANTE, dias_maximos=5))
        db.commit()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(20), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "5 días" in respuesta.json()["detail"]


def test_fecha_igual_al_limite_de_anticipacion_es_valida(client, solicitante):
    espacio_id = _crear_espacio()
    with SessionLocal() as db:
        db.add(ReglaAnticipacionRol(rol=RolReserva.ESTUDIANTE, dias_maximos=5))
        db.commit()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(5), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_rol_sin_anticipacion_configurada_no_tiene_limite(client, solicitante):
    espacio_id = _crear_espacio()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(120), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_espacio_con_responsable_exige_uno_valido(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio(requiere_responsable=True)
    estudiante = crear_usuario("otro-estudiante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)
    docente = crear_usuario("docente-reglas@reservas.test", Rol.SOLICITANTE, Cargo.DOCENTE)

    sin_responsable = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00"), headers=cabecera(solicitante)
    )
    con_estudiante = client.post(
        URL,
        json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", responsable_id=estudiante.id),
        headers=cabecera(solicitante),
    )
    con_docente = client.post(
        URL,
        json=_cuerpo(espacio_id, _dia(), "09:00", "10:00", responsable_id=docente.id),
        headers=cabecera(solicitante),
    )

    assert sin_responsable.status_code == 422
    assert con_estudiante.status_code == 422
    assert "docente" in con_estudiante.json()["detail"]
    assert con_docente.status_code == 201
    assert con_docente.json()["responsable"] == docente.nombre


# --------------------------------------------------------------------------- #
# HU-33: duración máxima y separación
# --------------------------------------------------------------------------- #
def test_duracion_por_encima_del_maximo_se_rechaza(client, solicitante):
    espacio_id = _crear_espacio(duracion_maxima_min=180)

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "08:00", "12:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "180" in respuesta.json()["detail"]


def test_duracion_igual_al_maximo_es_valida(client, solicitante):
    espacio_id = _crear_espacio(duracion_maxima_min=180)

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "08:00", "11:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_sin_duracion_maxima_no_se_limita(client, solicitante):
    espacio_id = _crear_espacio()

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "07:00", "12:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_separacion_entre_reservas_impide_el_horario_pegado(client, solicitante):
    espacio_id = _crear_espacio(separacion_min=15)
    fecha = datetime.fromisoformat(_dia()).replace(tzinfo=ZONA_COLOMBIA)
    _crear_reserva_directa(
        espacio_id,
        solicitante.id,
        datetime.combine(fecha.date(), time(8, 0), ZONA_COLOMBIA),
        datetime.combine(fecha.date(), time(10, 0), ZONA_COLOMBIA),
    )

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "10:00", "11:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 409
    assert "15 minutos" in respuesta.json()["detail"]
    assert "10:15" in respuesta.json()["detail"]


def test_sin_separacion_se_permiten_reservas_consecutivas(client, solicitante):
    espacio_id = _crear_espacio()
    fecha = datetime.fromisoformat(_dia()).replace(tzinfo=ZONA_COLOMBIA)
    _crear_reserva_directa(
        espacio_id,
        solicitante.id,
        datetime.combine(fecha.date(), time(8, 0), ZONA_COLOMBIA),
        datetime.combine(fecha.date(), time(10, 0), ZONA_COLOMBIA),
    )

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "10:00", "11:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


# --------------------------------------------------------------------------- #
# HU-21 y HU-34: franja de operación, días y usos diarios
# --------------------------------------------------------------------------- #
def test_fuera_de_la_franja_del_espacio_se_rechaza(client, solicitante):
    espacio_id = _crear_espacio(hora_apertura=time(8), hora_cierre=time(12))

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "13:00", "14:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "08:00" in respuesta.json()["detail"]
    assert "12:00" in respuesta.json()["detail"]


def test_dentro_de_la_franja_del_espacio_se_acepta(client, solicitante):
    espacio_id = _crear_espacio(hora_apertura=time(8), hora_cierre=time(12))

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


def test_dia_no_operable_se_rechaza(client, solicitante):
    hoy = datetime.now(ZONA_COLOMBIA).date()
    manana = hoy + timedelta(days=1)
    # El espacio solo opera el día de mañana, así que hoy + 2 no es operable
    espacio_id = _crear_espacio(dias_operacion=str(manana.isoweekday()))

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(2), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "no opera" in respuesta.json()["detail"]


def test_maximo_de_usos_por_dia_bloquea_el_siguiente(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio(max_usos_dia=1)
    otro = crear_usuario("otro-solicitante@reservas.test", Rol.SOLICITANTE, Cargo.ESTUDIANTE)

    primera = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "09:00", "10:00"), headers=cabecera(solicitante)
    )
    segunda = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "11:00", "12:00"), headers=cabecera(otro)
    )

    assert primera.status_code == 201
    assert segunda.status_code == 409
    assert "usos por día" in segunda.json()["detail"]


def test_la_disponibilidad_respeta_la_franja_del_espacio(client, solicitante):
    dentro = _crear_espacio(nombre=f"Dentro {uuid4().hex}", hora_apertura=time(8), hora_cierre=time(12))
    fuera = _crear_espacio(nombre=f"Fuera {uuid4().hex}", hora_apertura=time(14), hora_cierre=time(18))

    respuesta = client.get(
        "/api/v1/espacios/disponibles",
        params={"fecha": _dia(), "hora_inicio": "09:00", "hora_fin": "10:00"},
    )

    ids = [espacio["id"] for espacio in respuesta.json()]
    assert dentro in ids
    assert fuera not in ids


# --------------------------------------------------------------------------- #
# HU-35: autorización especial fuera de la franja
# --------------------------------------------------------------------------- #
def _autorizador(crear_usuario, email: str = "autoriza@reservas.test"):
    usuario = crear_usuario(email, Rol.APROBADOR, Cargo.COORDINADOR_LABORATORIOS)
    with SessionLocal() as db:
        from app.models.modelos import Usuario

        db.get(Usuario, usuario.id).puede_autorizar_especial = True
        db.commit()
    return usuario


def test_fuera_de_franja_con_autorizacion_especial_queda_pendiente(client, solicitante):
    espacio_id = _crear_espacio(
        hora_apertura=time(8), hora_cierre=time(12), admite_autorizacion_especial=True
    )

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "06:00", "07:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "PENDIENTE_AUTORIZACION"
    assert cuerpo["fuera_de_franja"] is True
    assert cuerpo["avisos"]


def test_autorizacion_especial_concede_y_pasa_a_pendiente(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio(
        hora_apertura=time(8), hora_cierre=time(12), admite_autorizacion_especial=True
    )
    autorizador = _autorizador(crear_usuario)
    creada = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "06:00", "07:00"), headers=cabecera(solicitante)
    ).json()

    bandeja = client.get(f"{URL}autorizaciones", headers=cabecera(autorizador))
    decision = client.post(
        f"{URL}{creada['id']}/autorizacion",
        json={"aprobar": True},
        headers=cabecera(autorizador),
    )

    assert bandeja.status_code == 200
    assert [item["id"] for item in bandeja.json()] == [creada["id"]]
    assert decision.status_code == 200
    assert decision.json()["solicitud"]["estado"] == "PENDIENTE"


def test_autorizacion_especial_negada_exige_motivo(client, solicitante, crear_usuario):
    espacio_id = _crear_espacio(
        hora_apertura=time(8), hora_cierre=time(12), admite_autorizacion_especial=True
    )
    autorizador = _autorizador(crear_usuario)
    creada = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "06:00", "07:00"), headers=cabecera(solicitante)
    ).json()

    sin_motivo = client.post(
        f"{URL}{creada['id']}/autorizacion",
        json={"aprobar": False},
        headers=cabecera(autorizador),
    )
    con_motivo = client.post(
        f"{URL}{creada['id']}/autorizacion",
        json={"aprobar": False, "motivo": "Sin personal de vigilancia"},
        headers=cabecera(autorizador),
    )

    assert sin_motivo.status_code == 422
    assert con_motivo.status_code == 200
    assert con_motivo.json()["solicitud"]["estado"] == "RECHAZADA"


def test_usuario_sin_permiso_no_ve_la_bandeja_de_autorizaciones(client, solicitante):
    respuesta = client.get(f"{URL}autorizaciones", headers=cabecera(solicitante))

    assert respuesta.status_code == 403


def test_sin_autorizacion_especial_el_espacio_rechaza_fuera_de_franja(client, solicitante):
    espacio_id = _crear_espacio(hora_apertura=time(8), hora_cierre=time(12))

    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(), "06:00", "07:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 422
    assert "08:00" in respuesta.json()["detail"]


# --------------------------------------------------------------------------- #
# HU-22 y HU-36: configuración
# --------------------------------------------------------------------------- #
def test_solo_el_admin_configura_las_reglas(client, solicitante):
    espacio_id = _crear_espacio()

    respuesta = client.put(
        f"{CONFIG}/espacios/{espacio_id}",
        json={"max_usos_dia": 3},
        headers=cabecera(solicitante),
    )

    assert respuesta.status_code == 403


def test_admin_configura_reglas_y_queda_el_historial(client, admin):
    espacio_id = _crear_espacio()

    respuesta = client.put(
        f"{CONFIG}/espacios/{espacio_id}",
        json={
            "hora_apertura": "08:00:00",
            "hora_cierre": "18:00:00",
            "dias_operacion": [1, 2, 3, 4, 5],
            "max_usos_dia": 4,
            "duracion_maxima_min": 120,
            "separacion_min": 10,
            "ocupacion_minima": 5,
            "requiere_responsable": True,
            "admite_autorizacion_especial": True,
        },
        headers=cabecera(admin),
    )
    historial = client.get(f"{CONFIG}/historial", params={"espacio_id": espacio_id}, headers=cabecera(admin))

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["dias_operacion"] == [1, 2, 3, 4, 5]
    assert cuerpo["max_usos_dia"] == 4
    assert cuerpo["hora_apertura"] == "08:00:00"
    assert historial.status_code == 200
    assert historial.json()[0]["usuario"] == admin.nombre


def test_franja_incompleta_se_rechaza(client, admin):
    espacio_id = _crear_espacio()

    respuesta = client.put(
        f"{CONFIG}/espacios/{espacio_id}",
        json={"hora_apertura": "08:00:00"},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 422


def test_ocupacion_minima_mayor_que_la_capacidad_se_rechaza(client, admin):
    espacio_id = _crear_espacio(capacidad=10)

    respuesta = client.put(
        f"{CONFIG}/espacios/{espacio_id}",
        json={"ocupacion_minima": 15},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 422


def test_admin_asocia_actividades_al_espacio(client, admin, solicitante):
    espacio_id = _crear_espacio()
    tipo_id = _crear_tipo_uso("Sustentación")

    respuesta = client.put(
        f"{CONFIG}/espacios/{espacio_id}",
        json={"tipos_uso_ids": [tipo_id]},
        headers=cabecera(admin),
    )
    consulta = client.get(f"{CONFIG}/espacios/{espacio_id}", headers=cabecera(solicitante))

    assert respuesta.status_code == 200
    assert [tipo["nombre"] for tipo in respuesta.json()["tipos_uso"]] == ["Sustentación"]
    assert consulta.status_code == 200
    assert consulta.json()["tipos_uso"][0]["id"] == tipo_id


def test_aplicar_reglas_a_todos_los_espacios_del_tipo(client, admin):
    primero = _crear_espacio(tipo=TipoEspacio.LABORATORIO)
    segundo = _crear_espacio(tipo=TipoEspacio.LABORATORIO)

    respuesta = client.put(
        f"{CONFIG}/espacios/por-tipo",
        json={"tipo": "LABORATORIO", "reglas": {"max_usos_dia": 2}},
        headers=cabecera(admin),
    )

    assert respuesta.status_code == 200
    assert {item["espacio_id"] for item in respuesta.json()} == {primero, segundo}
    assert all(item["max_usos_dia"] == 2 for item in respuesta.json())


def test_tipos_de_uso_duplicados_se_rechazan(client, admin):
    nombre = f"Taller {uuid4().hex}"
    primera = client.post(f"{CONFIG}/tipos-uso", json={"nombre": nombre}, headers=cabecera(admin))
    segunda = client.post(f"{CONFIG}/tipos-uso", json={"nombre": nombre}, headers=cabecera(admin))

    assert primera.status_code == 201
    assert segunda.status_code == 409


def test_tipo_de_uso_desactivado_sale_del_catalogo(client, admin, solicitante):
    creado = client.post(
        f"{CONFIG}/tipos-uso", json={"nombre": f"Feria {uuid4().hex}"}, headers=cabecera(admin)
    ).json()
    client.patch(
        f"{CONFIG}/tipos-uso/{creado['id']}", json={"activo": False}, headers=cabecera(admin)
    )

    activos = client.get(f"{CONFIG}/tipos-uso", headers=cabecera(solicitante))
    todos = client.get(
        f"{CONFIG}/tipos-uso", params={"incluir_inactivos": True}, headers=cabecera(admin)
    )

    assert creado["id"] not in [tipo["id"] for tipo in activos.json()]
    assert creado["id"] in [tipo["id"] for tipo in todos.json()]


# --------------------------------------------------------------------------- #
# HU-37: anticipación por rol
# --------------------------------------------------------------------------- #
def test_admin_configura_la_anticipacion_por_rol(client, admin):
    respuesta = client.put(
        f"{CONFIG}/anticipacion/ESTUDIANTE",
        json={"dias_maximos": 7},
        headers=cabecera(admin),
    )
    listado = client.get(f"{CONFIG}/anticipacion", headers=cabecera(admin))

    assert respuesta.status_code == 200
    assert respuesta.json() == {"rol": "ESTUDIANTE", "dias_maximos": 7}
    valores = {item["rol"]: item["dias_maximos"] for item in listado.json()}
    assert valores["ESTUDIANTE"] == 7
    assert valores["DIRECTOR"] is None


def test_anticipacion_no_positiva_se_rechaza(client, admin):
    respuesta = client.put(
        f"{CONFIG}/anticipacion/DOCENTE", json={"dias_maximos": 0}, headers=cabecera(admin)
    )

    assert respuesta.status_code == 422


def test_quitar_la_anticipacion_elimina_el_limite(client, admin, solicitante):
    client.put(f"{CONFIG}/anticipacion/ESTUDIANTE", json={"dias_maximos": 3}, headers=cabecera(admin))
    client.put(f"{CONFIG}/anticipacion/ESTUDIANTE", json={"dias_maximos": None}, headers=cabecera(admin))

    espacio_id = _crear_espacio()
    respuesta = client.post(
        URL, json=_cuerpo(espacio_id, _dia(60), "09:00", "10:00"), headers=cabecera(solicitante)
    )

    assert respuesta.status_code == 201


@pytest.mark.parametrize("rol", ["ESTUDIANTE", "DOCENTE", "COORDINADOR", "DIRECTOR"])
def test_la_anticipacion_lista_los_cuatro_roles(client, admin, rol):
    listado = client.get(f"{CONFIG}/anticipacion", headers=cabecera(admin))

    assert rol in [item["rol"] for item in listado.json()]
