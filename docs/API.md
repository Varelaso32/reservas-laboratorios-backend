# Reservas Laboratorios API: documentación de endpoints

Swagger: http://localhost:8000/docs

Este archivo se actualiza al terminar cada fase.

## Convenciones

- Rutas de negocio bajo /api/v1.
- Fechas y horas en hora de Colombia (-05:00).
- Errores con la forma {"detail": "mensaje"}.

## Cambios por fase

| Fase | Qué se agregó | Endpoints nuevos |
|---|---|---|
| 0 | Base de datos: conexión, 6 tablas y datos de prueba | Ninguno |

## Índice de endpoints

Aún no hay endpoints del negocio. Los primeros llegan con la HU-01.

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
activa mañana de 08:00 a 10:00 en el Laboratorio de Redes.
