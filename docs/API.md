# Reservas Laboratorios API: documentación de endpoints

Swagger: http://localhost:8000/docs
Esquema OpenAPI: http://localhost:8000/api/v1/openapi.json

Este archivo se actualiza al terminar cada fase.

## Convenciones

- Rutas de negocio bajo /api/v1.
- Fechas y horas en hora de Colombia (-05:00). Las respuestas devuelven fechas con zona, por ejemplo 2026-10-05T08:00:00-05:00.
- Errores de negocio con la forma {"detail": "mensaje"}.
- Errores de formato (campo faltante o de tipo incorrecto) los genera FastAPI: {"detail": [lista de errores por campo]}, con textos en inglés.
- Autenticación: token JWT en la cabecera Authorization: Bearer <token>.
  Se obtiene con POST /api/v1/auth/login y dura 60 minutos.
- En Swagger: botón "Authorize", correo en username y clave en password.
- Los endpoints de espacios siguen siendo públicos por ahora.

| Código | Significado |
|---|---|
| 401 | Falta el token, no es válido o expiró |
| 403 | El usuario no tiene el rol necesario o está inactivo |
| 404 | El recurso no existe, no está activo o el usuario no tiene acceso a él |
| 409 | Conflicto: el espacio está ocupado o ya existe una solicitud pendiente que se cruza |
| 422 | Datos de entrada inválidos |

## Cambios por fase

| Fase | Qué se agregó | Endpoints nuevos |
|---|---|---|
| 0 | Base de datos: conexión, 6 tablas y datos de prueba | Ninguno |
| 1 | HU-01: listar espacios y consultar disponibilidad | GET /api/v1/espacios/, GET /api/v1/espacios/disponibles |
| 2 | Login y roles con JWT | POST /api/v1/auth/login, GET /api/v1/auth/me |
| 3 | HU-04 y HU-05 (SCRUM-73, SCRUM-75): crear solicitud, validar disponibilidad y mis solicitudes. Registro CREADA en el historial | POST /api/v1/solicitudes/, GET /api/v1/solicitudes/mias, GET /api/v1/espacios/{espacio_id}/disponibilidad |
| 4 | HU-08 y HU-09 (SCRUM-77, SCRUM-79): pendientes del aprobador y detalle de una solicitud | GET /api/v1/solicitudes/pendientes, GET /api/v1/solicitudes/{solicitud_id} |

## Índice de endpoints

| Método | Ruta | Resumen | Rol | HU | Fase |
|---|---|---|---|---|---|
| GET | /api/v1/espacios/ | Listar espacios activos | Público | HU-01 | 1 |
| GET | /api/v1/espacios/disponibles | Consultar espacios disponibles | Público | HU-01 | 1 |
| GET | /api/v1/espacios/{espacio_id}/disponibilidad | Validar disponibilidad de un espacio | Público | HU-05 | 3 |
| POST | /api/v1/auth/login | Iniciar sesión | Público | Base | 2 |
| GET | /api/v1/auth/me | Usuario actual | Cualquiera con sesión | Base | 2 |
| POST | /api/v1/solicitudes/ | Crear solicitud de reserva | SOLICITANTE | HU-04, HU-05 | 3 |
| GET | /api/v1/solicitudes/mias | Mis solicitudes | SOLICITANTE | HU-10.6, HU-11.7 | 3 |
| GET | /api/v1/solicitudes/pendientes | Pendientes de mis espacios | APROBADOR | HU-08 | 4 |
| GET | /api/v1/solicitudes/{solicitud_id} | Detalle de una solicitud | APROBADOR (sus espacios), SOLICITANTE (las suyas), ADMIN (todas) | HU-09 | 4 |

## Autenticación

### POST /api/v1/auth/login

Inicia sesión y devuelve un token JWT. Se envía como formulario
(application/x-www-form-urlencoded), no como JSON.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| username | texto | Sí | Correo del usuario (no distingue mayúsculas) |
| password | texto | Sí | Clave |

Respuesta 200: access_token, token_type ("bearer"), expira_en (3600) y usuario
(id, nombre, email, rol y cargo).

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

## Espacios

### GET /api/v1/espacios/

Devuelve los laboratorios y salas activos. Los inactivos no aparecen.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| tipo | LABORATORIO / SALA | No | Filtra por tipo. Sin él trae ambos |

Respuesta 200: lista de espacios con id, nombre, tipo, capacidad y ubicacion.

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

### GET /api/v1/espacios/{espacio_id}/disponibilidad

HU-05. Indica si un espacio está libre en un horario, para avisar al usuario antes
de enviar la solicitud. Es informativo: al crear la solicitud se vuelve a validar.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| espacio_id | entero (en la ruta) | Sí | Espacio a validar |
| fecha | fecha (AAAA-MM-DD) | Sí | Día |
| hora_inicio | hora (HH:MM) | Sí | Inicio |
| hora_fin | hora (HH:MM) | Sí | Fin |

Respuesta 200: {"espacio_id": 1, "disponible": false, "mensaje": "El espacio ya se encuentra ocupado en ese horario"}

| Código | Cuándo |
|---|---|
| 200 | Validación hecha (disponible true o false) |
| 404 | El espacio no existe o no está activo |
| 422 | Horario inválido o en el pasado |

## Solicitudes

### POST /api/v1/solicitudes/

HU-04 y HU-05. Registra una solicitud en estado PENDIENTE. Solo rol SOLICITANTE.
Se envía como JSON.

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| espacio_id | entero | Sí | Espacio a reservar |
| fecha | fecha (AAAA-MM-DD) | Sí | Día de uso |
| hora_inicio | hora (HH:MM) | Sí | Inicio (hora de Colombia) |
| hora_fin | hora (HH:MM) | Sí | Fin (hora de Colombia) |
| proposito | texto (1 a 500) | Sí | Para qué se usará. No puede ser solo espacios |
| asistentes | entero mayor que 0 | Sí | No puede superar la capacidad del espacio |
| equipamiento | texto (hasta 500) | No | Equipos requeridos |

Validaciones, en este orden:
1. El espacio existe y está activo (si no, 404).
2. La hora de fin es mayor que la de inicio y el horario no está en el pasado (si no, 422).
3. Los asistentes no superan la capacidad (si no, 422).
4. El espacio no tiene una reserva activa que se cruce (si la tiene, 409 y no se registra nada).
5. El mismo usuario no tiene otra solicitud PENDIENTE para ese espacio en un horario que se cruce (si la tiene, 409).

Una solicitud pendiente de OTRO usuario no bloquea: el aprobador decide.

Respuesta 201: la solicitud (id, espacio_id, espacio_nombre, inicio, fin, proposito,
asistentes, equipamiento, estado, motivo_rechazo, fecha_decision, creada_en) más
"mensaje": "Solicitud #N registrada. Quedó en estado PENDIENTE."

La creación queda en el historial con la acción CREADA.

| Código | Cuándo |
|---|---|
| 201 | Solicitud registrada |
| 401 | No autenticado |
| 403 | El usuario no es SOLICITANTE |
| 404 | El espacio no existe o no está activo |
| 409 | El espacio está ocupado, o ya tienes una solicitud pendiente que se cruza |
| 422 | Datos inválidos |

Ejemplo de cuerpo:
{"espacio_id": 2, "fecha": "2026-10-05", "hora_inicio": "08:00", "hora_fin": "10:00", "proposito": "Práctica de redes", "asistentes": 15, "equipamiento": "Proyector"}

### GET /api/v1/solicitudes/mias

Devuelve las solicitudes del usuario que inició sesión, de la más reciente a la más
antigua. Solo rol SOLICITANTE. Sirve para que el solicitante vea si su solicitud fue
aprobada y el motivo si fue rechazada.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| estado | PENDIENTE / APROBADA / RECHAZADA / CANCELADA | No | Filtra por estado |

| Código | Cuándo |
|---|---|
| 200 | Lista de solicitudes (puede ser vacía) |
| 401 | No autenticado |
| 403 | El usuario no es SOLICITANTE |

### GET /api/v1/solicitudes/pendientes

HU-08. Solicitudes en estado PENDIENTE de los espacios que administra el aprobador
que inició sesión. Solo rol APROBADOR. No muestra solicitudes de otros espacios.

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| espacio_id | entero | No | Filtra por un espacio. Si es un espacio que no administra, devuelve [] |

Cada elemento trae: id, estado, solicitante (id, nombre, email, cargo), espacio
(id, nombre, tipo, capacidad, ubicacion), inicio, fin, asistentes, creada_en y
vencida. Orden: por hora de inicio, las más próximas primero.

vencida = true significa que la hora de inicio ya pasó: la solicitud ya no se puede aprobar.

| Código | Cuándo |
|---|---|
| 200 | Lista de pendientes (puede ser vacía) |
| 401 | No autenticado |
| 403 | El usuario no es APROBADOR |

### GET /api/v1/solicitudes/{solicitud_id}

HU-09. Detalle completo de una solicitud: todo lo de la lista de pendientes más
proposito, equipamiento, motivo_rechazo, decidido_por (nombre) y fecha_decision.

Quién puede verla:
- APROBADOR: solo solicitudes de los espacios que administra.
- SOLICITANTE: solo las suyas.
- ADMIN: todas.

| Código | Cuándo |
|---|---|
| 200 | Detalle de la solicitud |
| 401 | No autenticado |
| 404 | La solicitud no existe o el usuario no tiene acceso (mismo mensaje en ambos casos) |
| 422 | El id no es un número |

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
