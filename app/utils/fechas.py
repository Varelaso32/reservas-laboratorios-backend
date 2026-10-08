from datetime import time, timedelta, timezone

# Colombia no tiene horario de verano: -05:00 todo el año
ZONA_COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")

# Horario institucional para reservar, todos los días. Fuera de él no se puede
# solicitar un espacio; el tiempo que sobre al final del día queda sin usar.
HORA_APERTURA = time(7)
HORA_CIERRE = time(22)
