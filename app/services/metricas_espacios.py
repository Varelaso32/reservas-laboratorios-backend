"""Métricas de reservas por espacio dentro del horario institucional (todos los días)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoReserva
from app.models.modelos import Espacio, Reserva
from app.utils.fechas import HORA_APERTURA, HORA_CIERRE, ZONA_COLOMBIA

MINUTOS_DIA_OPERATIVO = (HORA_CIERRE.hour - HORA_APERTURA.hour) * 60


def listar_por_fecha(db: Session, fecha: date) -> list[dict]:
    """Devuelve las métricas de todos los espacios para una fecha local."""
    espacios = db.scalars(select(Espacio).order_by(Espacio.tipo, Espacio.nombre)).all()
    inicio_dia = datetime.combine(fecha, time.min, ZONA_COLOMBIA)
    fin_dia = inicio_dia + timedelta(days=1)

    filas = db.execute(
        select(Reserva.espacio_id, Reserva.inicio, Reserva.fin)
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < fin_dia,
            Reserva.fin > inicio_dia,
        )
        .order_by(Reserva.espacio_id, Reserva.inicio, Reserva.id)
    ).all()

    horario_apertura = datetime.combine(fecha, HORA_APERTURA, ZONA_COLOMBIA)
    horario_cierre = datetime.combine(fecha, HORA_CIERRE, ZONA_COLOMBIA)
    acumulados: dict[int, dict[str, float | int]] = {}

    for espacio_id, inicio, fin in filas:
        metricas = acumulados.setdefault(espacio_id, {"reservas_dia": 0, "minutos_reservados": 0.0})
        metricas["reservas_dia"] += 1
        inicio_ocupado = max(inicio, horario_apertura)
        fin_ocupado = min(fin, horario_cierre)
        if fin_ocupado > inicio_ocupado:
            metricas["minutos_reservados"] += (fin_ocupado - inicio_ocupado).total_seconds() / 60

    salida = []
    for espacio in espacios:
        metricas = acumulados.get(espacio.id, {"reservas_dia": 0, "minutos_reservados": 0.0})
        disponibles = MINUTOS_DIA_OPERATIVO if espacio.activo else 0
        reservados = round(float(metricas["minutos_reservados"]), 2)
        salida.append(
            {
                "id": espacio.id,
                "nombre": espacio.nombre,
                "tipo": espacio.tipo,
                "capacidad": espacio.capacidad,
                "ubicacion": espacio.ubicacion,
                "activo": espacio.activo,
                "fecha": fecha,
                "reservas_dia": int(metricas["reservas_dia"]),
                "minutos_reservados": reservados,
                "minutos_disponibles": disponibles,
                "porcentaje_ocupacion": round(reservados / disponibles * 100, 2) if disponibles else None,
            }
        )
    return salida
