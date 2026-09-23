# Reservas Laboratorios API: documentación de endpoints

Swagger: http://localhost:8000/docs

Este archivo se actualiza al terminar cada fase.

## Convenciones

- Rutas de negocio bajo /api/v1.
- Fechas y horas en hora de Colombia (-05:00).
- Errores con la forma {"detail": "mensaje"}.
- Por ahora los endpoints no piden login. Se protegen en la fase de autenticación.

## Cambios por fase

| Fase | Qué se agregó | Endpoints nuevos |
|---|---|---|
| 0 | Base de datos: conexión, 6 tablas y datos de prueba | Ninguno |
| 1 | HU-01: listar espacios y consultar disponibilidad | GET /api/v1/espacios/, GET /api/v1/espacios/disponibles |

## Índice de endpoints

| Método | Ruta | Resumen | HU | Fase |
|---|---|---|---|---|
| GET | /api/v1/espacios/ | Listar espacios activos | HU-01 | 1 |
| GET | /api/v1/espacios/disponibles | Consultar espacios disponibles | HU-01 | 1 |

## Espacios

### GET /api/v1/espacios/

Devuelve los laboratorios y salas activos. Los inactivos no aparecen.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| tipo | LABORATORIO / SALA | No | Filtra por tipo. Sin él trae ambos |

Respuesta 200: lista de espacios con id, nombre, tipo, capacidad y ubicacion.

| Código | Cuándo |
|---|---|
| 200 | Consulta correcta |
| 422 | El tipo no es LABORATORIO ni SALA |

Ejemplo: curl "http://localhost:8000/api/v1/espacios/?tipo=LABORATORIO"

### GET /api/v1/espacios/disponibles

Devuelve los espacios activos que no tienen una reserva activa que se cruce con el
horario pedido.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| fecha | fecha (AAAA-MM-DD) | Sí | Día a consultar |
| hora_inicio | hora (HH:MM) | Sí | Inicio del rango |
| hora_fin | hora (HH:MM) | Sí | Fin del rango |
| tipo | LABORATORIO / SALA | No | Filtra por tipo |

Reglas:
- Una reserva que se cruza, aunque sea parcialmente, deja el espacio fuera.
- Una reserva contigua (termina justo cuando empieza la consulta) no bloquea.
- Las reservas canceladas no bloquean.
- Sin espacios disponibles: 200 con lista vacía [].

| Código | Cuándo |
|---|---|
| 200 | Consulta correcta (puede ser lista vacía) |
| 422 | Falta un parámetro, la hora de fin no es mayor que la de inicio o la fecha ya pasó |

Ejemplo: curl "http://localhost:8000/api/v1/espacios/disponibles?fecha=2026-10-05&hora_inicio=08:00&hora_fin=10:00"

## Base de datos (referencia)

| Tabla | Qué guarda |
|---|---|
| usuario | Usuarios con su rol (SOLICITANTE, APROBADOR, ADMIN) y cargo |
| espacio | Laboratorios y salas: tipo, capacidad, ubicación y si están activos |
| espacio_aprobador | Qué aprobadores gestionan cada espacio |
| solicitud | Solicitudes de reserva y su estado (PENDIENTE, APROBADA, RECHAZADA, CANCELADA) |
| reserva | Reservas generadas al aprobar. La BD impide dos reservas activas cruzadas en el mismo espacio |
| trazabilidad | Historial de acciones sobre cada solicitud. No se puede modificar ni borrar |

Datos de prueba (docker compose exec api python -m app.utils.datos_prueba):
6 usuarios con dominio @reservas.test, 6 espacios (uno inactivo) y una reserva
activa al día siguiente de 08:00 a 10:00 en el Laboratorio de Redes.
