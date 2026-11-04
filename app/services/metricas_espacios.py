"""Métricas de reservas por espacio dentro de su franja de operación (HU-21, HU-36)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import EstadoReserva
from app.models.modelos import Reserva, Usuario
from app.services import reglas
from app.services.espacios import visibles_para
from app.utils.fechas import ZONA_COLOMBIA


def _franja_del_dia(espacio, fecha: date) -> tuple[datetime, datetime] | None:
    """Rango operativo del espacio en esa fecha, o None si ese día no opera."""
    dias = reglas.dias_de(espacio)
    if dias and fecha.isoweekday() not in dias:
        return None
    apertura, cierre = reglas.franja_de(espacio)
    return (
        datetime.combine(fecha, apertura, ZONA_COLOMBIA),
        datetime.combine(fecha, cierre, ZONA_COLOMBIA),
    )


def listar_por_fecha(db: Session, usuario: Usuario, fecha: date) -> list[dict]:
    """Métricas de una fecha local: el ADMIN ve todos los espacios, el APROBADOR los suyos."""
    espacios = db.scalars(visibles_para(usuario)).all()
    inicio_dia = datetime.combine(fecha, time.min, ZONA_COLOMBIA)
    fin_dia = inicio_dia + timedelta(days=1)

    filas = db.execute(
        select(Reserva.espacio_id, Reserva.inicio, Reserva.fin)
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.espacio_id.in_([espacio.id for espacio in espacios]),
            Reserva.inicio < fin_dia,
            Reserva.fin > inicio_dia,
        )
        .order_by(Reserva.espacio_id, Reserva.inicio, Reserva.id)
    ).all()

    acumulados: dict[int, dict[str, float | int]] = {}
    for espacio_id, _, _ in filas:
        metricas = acumulados.setdefault(espacio_id, {"reservas_dia": 0, "minutos_reservados": 0.0})
        metricas["reservas_dia"] += 1

    salida = []
    for espacio in espacios:
        metricas = acumulados.get(espacio.id, {"reservas_dia": 0, "minutos_reservados": 0.0})
        franja = _franja_del_dia(espacio, fecha) if espacio.activo else None

        if franja is not None:
            apertura, cierre = franja
            for espacio_id, inicio, fin in filas:
                if espacio_id != espacio.id:
                    continue
                inicio_ocupado = max(inicio, apertura)
                fin_ocupado = min(fin, cierre)
                if fin_ocupado > inicio_ocupado:
                    metricas["minutos_reservados"] += (fin_ocupado - inicio_ocupado).total_seconds() / 60
            disponibles = int((cierre - apertura).total_seconds() / 60)
        else:
            disponibles = 0

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
