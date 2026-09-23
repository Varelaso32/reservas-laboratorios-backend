# Reservas Laboratorios API: documentación de endpoints

Swagger: http://localhost:8000/docs
Esquema OpenAPI: http://localhost:8000/api/v1/openapi.json

Este archivo se actualiza al terminar cada fase.

## Convenciones

- Rutas de negocio bajo /api/v1.
- Fechas y horas en hora de Colombia (-05:00).
- Errores con la forma {"detail": "mensaje"}.
- Autenticación: token JWT en la cabecera Authorization: Bearer <token>.
  Se obtiene con POST /api/v1/auth/login y dura 60 minutos.
- En Swagger: botón "Authorize", correo en username y clave en password.
- Los endpoints de espacios (fase 1) siguen siendo públicos por ahora.

| Código | Significado |
|---|---|
| 401 | Falta el token, no es válido o expiró |
| 403 | El usuario no tiene el rol necesario o está inactivo |
| 422 | Datos de entrada inválidos |

## Cambios por fase

| Fase | Qué se agregó | Endpoints nuevos |
|---|---|---|
| 0 | Base de datos: conexión, 6 tablas y datos de prueba | Ninguno |
| 1 | HU-01: listar espacios y consultar disponibilidad | GET /api/v1/espacios/, GET /api/v1/espacios/disponibles |
| 2 | Login y roles con JWT | POST /api/v1/auth/login, GET /api/v1/auth/me |

## Índice de endpoints

| Método | Ruta | Resumen | Requiere login | HU | Fase |
|---|---|---|---|---|---|
| GET | /api/v1/espacios/ | Listar espacios activos | No | HU-01 | 1 |
| GET | /api/v1/espacios/disponibles | Consultar espacios disponibles | No | HU-01 | 1 |
| POST | /api/v1/auth/login | Iniciar sesión | No | Base | 2 |
| GET | /api/v1/auth/me | Usuario actual | Sí | Base | 2 |

## Autenticación

### POST /api/v1/auth/login

Inicia sesión y devuelve un token JWT. Se envía como formulario
(application/x-www-form-urlencoded), no como JSON.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| username | texto | Sí | Correo del usuario (no distingue mayúsculas) |
| password | texto | Sí | Clave |

Respuesta 200:

| Campo | Descripción |
|---|---|
| access_token | Token JWT |
| token_type | Siempre "bearer" |
| expira_en | Segundos de vigencia (3600) |
| usuario | id, nombre, email, rol y cargo |

| Código | Cuándo |
|---|---|
| 200 | Sesión iniciada |
| 401 | Correo o contraseña incorrectos (mismo mensaje en ambos casos) |
| 403 | El usuario está inactivo |
| 422 | Falta el correo o la clave, o se envió como JSON |

Ejemplo: curl -X POST "http://localhost:8000/api/v1/auth/login" -d "username=estudiante@reservas.test&password=Reservas2026*"

### GET /api/v1/auth/me

Devuelve los datos del usuario dueño del token: id, nombre, email, rol y cargo.

| Código | Cuándo |
|---|---|
| 200 | Token válido |
| 401 | Falta el token, no es válido, expiró o el usuario fue desactivado |

Ejemplo: curl "http://localhost:8000/api/v1/auth/me" -H "Authorization: Bearer <token>"

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

## Usuarios de prueba

Clave de todos: Reservas2026*

| Correo | Rol | Cargo |
|---|---|---|
| admin@reservas.test | ADMIN | Administrador del Sistema |
| coordinador.labs@reservas.test | APROBADOR | Coordinador de Laboratorios (gestiona los 3 laboratorios) |
| admin.salas@reservas.test | APROBADOR | Administrador de Sala (gestiona las 3 salas) |
| estudiante@reservas.test | SOLICITANTE | Estudiante |
| docente@reservas.test | SOLICITANTE | Docente |
| administrativo@reservas.test | SOLICITANTE | Administrativo |

## Base de datos (referencia)

| Tabla | Qué guarda |
|---|---|
| usuario | Usuarios con su rol (SOLICITANTE, APROBADOR, ADMIN) y cargo |
| espacio | Laboratorios y salas: tipo, capacidad, ubicación y si están activos |
| espacio_aprobador | Qué aprobadores gestionan cada espacio |
| solicitud | Solicitudes de reserva y su estado (PENDIENTE, APROBADA, RECHAZADA, CANCELADA) |
| reserva | Reservas generadas al aprobar. La BD impide dos reservas activas cruzadas en el mismo espacio |
| trazabilidad | Historial de acciones sobre cada solicitud. No se puede modificar ni borrar |

Datos de prueba:
- docker compose exec api python -m app.utils.datos_prueba (usuarios, espacios y una reserva de ejemplo)
- docker compose exec api python -m app.utils.claves_prueba (asigna la clave de prueba)

Configuración para producción (variables de entorno del contenedor, NO del .env):
- JWT_SECRET: clave para firmar los tokens. Obligatoria en producción.
- JWT_EXPIRA_MINUTOS: vigencia del token (por defecto 60).
