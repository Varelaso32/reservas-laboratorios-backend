"""Reportes analíticos y tablero del Administrador (HU-15, HU-24, HU-36)."""
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import (
    EstadoReserva,
    EstadoSolicitud,
    EstadoSolicitudRecurso,
)
from app.models.modelos import (
    Espacio,
    RegistroConfiguracion,
    Reserva,
    Solicitud,
    SolicitudRecurso,
    Trazabilidad,
    Usuario,
)
from app.services import reglas
from app.utils.fechas import ZONA_COLOMBIA

DIAS_CORTOS = {1: "Lun", 2: "Mar", 3: "Mié", 4: "Jue", 5: "Vie", 6: "Sáb", 7: "Dom"}
DIAS_LARGOS = {
    1: "Lunes",
    2: "Martes",
    3: "Miércoles",
    4: "Jueves",
    5: "Viernes",
    6: "Sábado",
    7: "Domingo",
}

# Franjas de dos horas dentro del horario institucional (07:00 a 22:00)
FRANJAS = ((7, 9), (9, 11), (11, 13), (13, 15), (15, 17), (17, 19), (19, 22))

MAXIMO_DIAS = 366


class ErrorReporte(Exception):
    def __init__(self, codigo: int, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _rango(
    desde: date | None, hasta: date | None
) -> tuple[date, date, datetime, datetime]:
    """Valida el periodo y lo convierte al rango local [inicio, fin)."""
    hoy = datetime.now(ZONA_COLOMBIA).date()
    hasta = hasta or hoy
    desde = desde or hasta - timedelta(days=6)
    if desde > hasta:
        raise ErrorReporte(422, "La fecha inicial no puede ser posterior a la fecha final")
    if (hasta - desde).days > MAXIMO_DIAS:
        raise ErrorReporte(422, "El periodo máximo de un reporte es de un año")
    inicio = datetime.combine(desde, time.min, ZONA_COLOMBIA)
    fin = datetime.combine(hasta + timedelta(days=1), time.min, ZONA_COLOMBIA)
    return desde, hasta, inicio, fin


def periodo_efectivo(desde: date | None, hasta: date | None) -> tuple[date, date]:
    """Periodo realmente cubierto, aplicando los valores por defecto."""
    desde, hasta, _, _ = _rango(desde, hasta)
    return desde, hasta


def _franja_minutos(espacio: Espacio, dia: date) -> int:
    """Minutos operables del espacio en ese día (0 si no opera)."""
    dias = reglas.dias_de(espacio)
    if dias and dia.isoweekday() not in dias:
        return 0
    apertura, cierre = reglas.franja_de(espacio)
    return int(
        (
            datetime.combine(dia, cierre, ZONA_COLOMBIA)
            - datetime.combine(dia, apertura, ZONA_COLOMBIA)
        ).total_seconds()
        // 60
    )


def _solape_minutos(espacio: Espacio, inicio: datetime, fin: datetime) -> float:
    """Minutos de la reserva que caen dentro de la franja operable del espacio."""
    dia = inicio.astimezone(ZONA_COLOMBIA).date()
    dias = reglas.dias_de(espacio)
    if dias and dia.isoweekday() not in dias:
        return 0.0
    apertura, cierre = reglas.franja_de(espacio)
    inicio_franja = datetime.combine(dia, apertura, ZONA_COLOMBIA)
    fin_franja = datetime.combine(dia, cierre, ZONA_COLOMBIA)
    inicio_util = max(inicio, inicio_franja)
    fin_util = min(fin, fin_franja)
    if fin_util <= inicio_util:
        return 0.0
    return (fin_util - inicio_util).total_seconds() / 60


def _hora(valor: datetime) -> str:
    return valor.astimezone(ZONA_COLOMBIA).strftime("%H:%M")


def _reservas_del_rango(db: Session, inicio: datetime, fin: datetime):
    return db.execute(
        select(
            Reserva.id,
            Reserva.espacio_id,
            Reserva.usuario_id,
            Reserva.inicio,
            Reserva.fin,
            Reserva.estado,
        ).where(Reserva.inicio < fin, Reserva.fin > inicio)
    ).all()


def resumen_semanal(
    db: Session, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """Reservas, cancelaciones, no-shows y ocupación por día (tarjeta semanal)."""
    desde, hasta, inicio, fin = _rango(desde, hasta)
    espacios = list(db.scalars(select(Espacio).where(Espacio.activo.is_(True))))
    por_id = {espacio.id: espacio for espacio in espacios}
    reservas = _reservas_del_rango(db, inicio, fin)

    filas: list[dict] = []
    dia = desde
    while dia <= hasta:
        disponibles = sum(_franja_minutos(espacio, dia) for espacio in espacios)
        minutos = 0.0
        total = canceladas = no_shows = 0
        for _, espacio_id, _, reserva_inicio, reserva_fin, estado in reservas:
            if reserva_inicio.astimezone(ZONA_COLOMBIA).date() != dia:
                continue
            total += 1
            if estado == EstadoReserva.CANCELADA:
                canceladas += 1
                continue
            if estado == EstadoReserva.NO_ASISTIO:
                no_shows += 1
                continue
            espacio = por_id.get(espacio_id)
            if espacio is not None:
                minutos += _solape_minutos(espacio, reserva_inicio, reserva_fin)
        filas.append(
            {
                "fecha": dia,
                "dia": DIAS_CORTOS[dia.isoweekday()],
                "reservas": total,
                "cancelaciones": canceladas,
                "no_shows": no_shows,
                "tasa_ocupacion": round(minutos / disponibles * 100, 2) if disponibles else 0.0,
            }
        )
        dia += timedelta(days=1)
    return filas


def ocupacion(
    db: Session,
    desde: date | None = None,
    hasta: date | None = None,
    espacio_id: int | None = None,
) -> list[dict]:
    """Uso de cada espacio en el periodo: reservas, horas y tasa de ocupación."""
    desde, hasta, inicio, fin = _rango(desde, hasta)
    consulta = select(Espacio).where(Espacio.activo.is_(True))
    if espacio_id is not None:
        consulta = select(Espacio).where(Espacio.id == espacio_id)
    espacios = list(db.scalars(consulta))
    if espacio_id is not None and not espacios:
        raise ErrorReporte(404, "El espacio indicado no existe")

    reservas = [
        fila
        for fila in _reservas_del_rango(db, inicio, fin)
        if fila.estado == EstadoReserva.ACTIVA
    ]
    dias = [desde + timedelta(days=indice) for indice in range((hasta - desde).days + 1)]

    salida: list[dict] = []
    for espacio in espacios:
        disponibles = sum(_franja_minutos(espacio, dia) for dia in dias)
        propias = [fila for fila in reservas if fila.espacio_id == espacio.id]
        minutos = sum(
            _solape_minutos(espacio, fila.inicio, fila.fin) for fila in propias
        )
        salida.append(
            {
                "espacio_id": espacio.id,
                "espacio": espacio.nombre,
                "tipo": espacio.tipo.value,
                "reservas": len(propias),
                "horas_reservadas": round(minutos / 60, 2),
                "horas_disponibles": round(disponibles / 60, 2),
                "tasa_ocupacion": round(minutos / disponibles * 100, 2) if disponibles else 0.0,
            }
        )
    return sorted(salida, key=lambda fila: fila["tasa_ocupacion"], reverse=True)


def actividad_usuarios(
    db: Session, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """Reservas, cancelaciones y no-shows agrupados por usuario."""
    _, _, inicio, fin = _rango(desde, hasta)
    reservas = _reservas_del_rango(db, inicio, fin)

    acumulado: dict[int, dict[str, int]] = {}
    for fila in reservas:
        datos = acumulado.setdefault(
            fila.usuario_id, {"reservas": 0, "cancelaciones": 0, "no_shows": 0}
        )
        datos["reservas"] += 1
        if fila.estado == EstadoReserva.CANCELADA:
            datos["cancelaciones"] += 1
        elif fila.estado == EstadoReserva.NO_ASISTIO:
            datos["no_shows"] += 1

    usuarios = {
        usuario.id: usuario
        for usuario in db.scalars(
            select(Usuario).where(Usuario.id.in_(list(acumulado.keys()) or [0]))
        )
    }
    salida = [
        {
            "usuario_id": usuario_id,
            "nombre": usuarios[usuario_id].nombre if usuario_id in usuarios else "Usuario eliminado",
            "email": usuarios[usuario_id].email if usuario_id in usuarios else "",
            "rol": usuarios[usuario_id].rol.value if usuario_id in usuarios else "",
            **datos,
        }
        for usuario_id, datos in acumulado.items()
    ]
    return sorted(salida, key=lambda fila: (-fila["reservas"], fila["nombre"]))


def no_shows(
    db: Session, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """Reservas en las que el solicitante no se presentó."""
    _, _, inicio, fin = _rango(desde, hasta)
    filas = db.execute(
        select(Reserva, Espacio.nombre, Usuario.nombre)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .join(Usuario, Usuario.id == Reserva.usuario_id)
        .where(
            Reserva.inicio < fin,
            Reserva.fin > inicio,
            Reserva.estado == EstadoReserva.NO_ASISTIO,
        )
        .order_by(Reserva.inicio.desc())
    ).all()
    return [
        {
            "reserva_id": reserva.id,
            "fecha": reserva.inicio.astimezone(ZONA_COLOMBIA).date(),
            "inicio": _hora(reserva.inicio),
            "fin": _hora(reserva.fin),
            "espacio": espacio,
            "usuario": usuario,
            "estado": "NO_ASISTIO",
        }
        for reserva, espacio, usuario in filas
    ]


def picos_demanda(
    db: Session, desde: date | None = None, hasta: date | None = None
) -> dict:
    """Días y franjas horarias con más reservas activas."""
    _, _, inicio, fin = _rango(desde, hasta)
    reservas = [
        fila
        for fila in _reservas_del_rango(db, inicio, fin)
        if fila.estado == EstadoReserva.ACTIVA
    ]

    por_dia: dict[int, int] = dict.fromkeys(DIAS_LARGOS, 0)
    por_franja: dict[str, int] = {}
    for fila in reservas:
        local = fila.inicio.astimezone(ZONA_COLOMBIA)
        por_dia[local.isoweekday()] += 1
        hora = local.hour
        for desde_hora, hasta_hora in FRANJAS:
            if desde_hora <= hora < hasta_hora:
                etiqueta = f"{desde_hora:02d}:00 – {hasta_hora:02d}:00"
                por_franja[etiqueta] = por_franja.get(etiqueta, 0) + 1
                break
    return {
        "por_dia": [
            {"dia": DIAS_LARGOS[numero], "reservas": por_dia[numero]}
            for numero in sorted(DIAS_LARGOS)
        ],
        "por_franja": [
            {"franja": franja, "reservas": por_franja.get(franja, 0)}
            for franja in (
                f"{desde_hora:02d}:00 – {hasta_hora:02d}:00"
                for desde_hora, hasta_hora in FRANJAS
            )
        ],
    }


def auditoria(
    db: Session, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """Acciones sobre solicitudes y cambios de configuración en el periodo."""
    _, _, inicio, fin = _rango(desde, hasta)
    filas: list[dict] = []

    acciones = db.execute(
        select(Trazabilidad, Usuario.nombre)
        .join(Usuario, Usuario.id == Trazabilidad.usuario_id)
        .where(Trazabilidad.fecha >= inicio, Trazabilidad.fecha < fin)
    ).all()
    for traza, usuario in acciones:
        filas.append(
            {
                "fecha": traza.fecha,
                "usuario": usuario,
                "origen": "SOLICITUD",
                "accion": traza.accion.value,
                "entidad": f"Solicitud #{traza.solicitud_id}",
                "detalle": traza.detalle,
            }
        )

    cambios = db.execute(
        select(RegistroConfiguracion, Usuario.nombre)
        .join(Usuario, Usuario.id == RegistroConfiguracion.usuario_id)
        .where(
            RegistroConfiguracion.fecha >= inicio,
            RegistroConfiguracion.fecha < fin,
        )
    ).all()
    for registro, usuario in cambios:
        filas.append(
            {
                "fecha": registro.fecha,
                "usuario": usuario,
                "origen": "CONFIGURACION",
                "accion": "CAMBIO",
                "entidad": registro.entidad,
                "detalle": registro.detalle,
            }
        )

    return sorted(filas, key=lambda fila: fila["fecha"], reverse=True)


def dashboard(db: Session) -> dict:
    """Indicadores del tablero del Administrador."""
    ahora = datetime.now(ZONA_COLOMBIA)
    hoy = ahora.date()
    inicio_dia = datetime.combine(hoy, time.min, ZONA_COLOMBIA)
    fin_dia = inicio_dia + timedelta(days=1)
    inicio_mes = datetime.combine(hoy.replace(day=1), time.min, ZONA_COLOMBIA)

    espacios = list(db.scalars(select(Espacio).where(Espacio.activo.is_(True))))
    por_id = {espacio.id: espacio for espacio in espacios}
    reservas_hoy = [
        fila
        for fila in _reservas_del_rango(db, inicio_dia, fin_dia)
        if fila.estado == EstadoReserva.ACTIVA
    ]
    disponibles = sum(_franja_minutos(espacio, hoy) for espacio in espacios)
    minutos = sum(
        _solape_minutos(por_id[fila.espacio_id], fila.inicio, fila.fin)
        for fila in reservas_hoy
        if fila.espacio_id in por_id
    )

    proximas = db.execute(
        select(Reserva, Espacio.nombre, Usuario.nombre)
        .join(Espacio, Espacio.id == Reserva.espacio_id)
        .join(Usuario, Usuario.id == Reserva.usuario_id)
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio < fin_dia,
            Reserva.fin > ahora,
        )
        .order_by(Reserva.inicio)
        .limit(6)
    ).all()

    hace_30 = ahora - timedelta(days=30)
    top = db.execute(
        select(Espacio.nombre, func.count(Reserva.id))
        .join(Reserva, Reserva.espacio_id == Espacio.id)
        .where(
            Reserva.estado == EstadoReserva.ACTIVA,
            Reserva.inicio >= hace_30,
        )
        .group_by(Espacio.nombre)
        .order_by(func.count(Reserva.id).desc())
        .limit(5)
    ).all()

    return {
        "reservas_hoy": len(reservas_hoy),
        "pendientes": db.scalar(
            select(func.count(Solicitud.id)).where(Solicitud.estado == EstadoSolicitud.PENDIENTE)
        )
        or 0,
        "no_shows_mes": db.scalar(
            select(func.count(Reserva.id)).where(
                Reserva.estado == EstadoReserva.NO_ASISTIO,
                Reserva.inicio >= inicio_mes,
            )
        )
        or 0,
        "ocupacion_hoy": round(minutos / disponibles * 100, 2) if disponibles else 0.0,
        "usuarios_activos": db.scalar(
            select(func.count(Usuario.id)).where(Usuario.activo.is_(True))
        )
        or 0,
        "espacios_activos": len(espacios),
        "recursos_pendientes": db.scalar(
            select(func.count(SolicitudRecurso.id)).where(
                SolicitudRecurso.estado == EstadoSolicitudRecurso.PENDIENTE
            )
        )
        or 0,
        "proximas_reservas": [
            {
                "id": reserva.id,
                "espacio": espacio,
                "usuario": usuario,
                "inicio": _hora(reserva.inicio),
                "fin": _hora(reserva.fin),
                "estado": reserva.estado.value,
            }
            for reserva, espacio, usuario in proximas
        ],
        "serie_semanal": resumen_semanal(db, hoy - timedelta(days=6), hoy),
        "top_espacios": [
            {"espacio": nombre, "reservas": total} for nombre, total in top
        ],
    }
