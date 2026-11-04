"""Esquemas de reportes y del tablero administrativo."""
from datetime import date, datetime

from pydantic import BaseModel, Field


class ResumenDiaOut(BaseModel):
    fecha: date = Field(description="Día del resumen")
    dia: str = Field(description="Nombre corto del día", examples=["Lun"])
    reservas: int = Field(description="Reservas registradas ese día (todos los estados)")
    cancelaciones: int = Field(description="Reservas canceladas ese día")
    no_shows: int = Field(description="Reservas marcadas como no asistió")
    tasa_ocupacion: float = Field(description="Porcentaje de ocupación de los espacios activos")


class OcupacionEspacioOut(BaseModel):
    espacio_id: int
    espacio: str
    tipo: str
    reservas: int
    horas_reservadas: float
    horas_disponibles: float
    tasa_ocupacion: float


class ActividadUsuarioOut(BaseModel):
    usuario_id: int
    nombre: str
    email: str
    rol: str
    reservas: int
    cancelaciones: int
    no_shows: int


class NoShowOut(BaseModel):
    reserva_id: int
    fecha: date
    inicio: str = Field(description="Hora de inicio en formato HH:MM")
    fin: str
    espacio: str
    usuario: str
    estado: str


class FranjaDemandaOut(BaseModel):
    franja: str = Field(examples=["07:00 – 09:00"])
    reservas: int


class DiaDemandaOut(BaseModel):
    dia: str = Field(examples=["Lunes"])
    reservas: int


class PicosDemandaOut(BaseModel):
    por_dia: list[DiaDemandaOut]
    por_franja: list[FranjaDemandaOut]


class AuditoriaOut(BaseModel):
    fecha: datetime
    usuario: str
    origen: str = Field(description="SOLICITUD o CONFIGURACION")
    accion: str
    entidad: str
    detalle: str | None


class ProximaReservaOut(BaseModel):
    id: int
    espacio: str
    usuario: str
    inicio: str
    fin: str
    estado: str


class TopEspacioOut(BaseModel):
    espacio: str
    reservas: int


class DashboardOut(BaseModel):
    reservas_hoy: int
    pendientes: int
    no_shows_mes: int
    ocupacion_hoy: float
    usuarios_activos: int
    espacios_activos: int
    recursos_pendientes: int
    proximas_reservas: list[ProximaReservaOut]
    serie_semanal: list[ResumenDiaOut]
    top_espacios: list[TopEspacioOut]
