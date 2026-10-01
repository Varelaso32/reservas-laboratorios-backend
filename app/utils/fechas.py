from datetime import timedelta, timezone

# Colombia no tiene horario de verano: -05:00 todo el año
ZONA_COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")
