# Guía de consumo de la API de Reservas de Laboratorios

Esta guía explica cómo llamar cada endpoint de la API: qué enviar, qué devuelve,
qué errores esperar y ejemplos listos para copiar (curl, JavaScript y PowerShell).

La referencia corta de cada endpoint está en `docs/API.md`. Esta guía la complementa
con ejemplos de consumo.

---

## 1. Datos de conexión

| Qué | Valor |
|---|---|
| URL base | `http://localhost:8000/api/v1` |
| Swagger (probar en el navegador) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Esquema OpenAPI (JSON) | http://localhost:8000/api/v1/openapi.json |

El esquema OpenAPI está en `/api/v1/openapi.json`, no en `/openapi.json`. Si usas
un generador de clientes (openapi-generator, orval, etc.), apúntalo a esa URL.

### Levantar la API y cargar datos de prueba

```bash
docker compose up -d
docker compose exec api python -m app.utils.crear_tablas
docker compose exec api python -m app.utils.datos_prueba
docker compose exec api python -m app.utils.claves_prueba
```

Los tres scripts se pueden correr varias veces sin duplicar datos.

### Usuarios de prueba

Clave de todos: `Reservas2026*`

| Correo | Rol | Qué puede hacer |
|---|---|---|
| `estudiante@reservas.test` | SOLICITANTE | Crear solicitudes, ver las suyas y sus reservas |
| `docente@reservas.test` | SOLICITANTE | Igual que el estudiante |
| `administrativo@reservas.test` | SOLICITANTE | Igual que el estudiante |
| `coordinador.labs@reservas.test` | APROBADOR | Aprobar o rechazar solicitudes de los 3 laboratorios |
| `admin.salas@reservas.test` | APROBADOR | Aprobar o rechazar solicitudes de las 3 salas |
| `admin@reservas.test` | ADMIN | Ver el detalle y el historial de todo |

---

## 2. Convenciones

### Autenticación

1. Se inicia sesión con `POST /auth/login` y se recibe un `access_token` (JWT).
2. Ese token se envía en cada petición protegida, en la cabecera:
   `Authorization: Bearer <access_token>`
3. El token dura 60 minutos (`expira_en: 3600`). Cuando vence, la API responde 401
   y hay que volver a iniciar sesión. No hay endpoint para renovar el token.

Si un usuario es desactivado, pierde el acceso de inmediato aunque su token no haya
vencido.

### Formato de los datos

- Las peticiones con cuerpo van en JSON (`Content-Type: application/json`), **excepto
  el login**, que va como formulario (`application/x-www-form-urlencoded`).
- Las fechas se envían como `AAAA-MM-DD` y las horas como `HH:MM`, en hora de Colombia.
- Las respuestas devuelven fecha y hora con zona, por ejemplo `2026-10-05T08:00:00-05:00`.

### Errores

Hay dos formatos de error:

**Errores de negocio** (401, 403, 404, 409 y algunos 422): un texto en español.

```json
{"detail": "El espacio ya está ocupado en ese horario"}
```

**Errores de formato** (422 que genera FastAPI cuando falta un campo o tiene el tipo
incorrecto): una lista, con textos en inglés.

```json
{
  "detail": [
    {"type": "missing", "loc": ["body", "proposito"], "msg": "Field required", "input": {}}
  ]
}
```

Para mostrar el error al usuario, revisa si `detail` es texto o lista:

```js
function mensajeDeError(cuerpo) {
  if (typeof cuerpo.detail === "string") return cuerpo.detail;
  if (Array.isArray(cuerpo.detail)) {
    return cuerpo.detail.map(e => `${e.loc.at(-1)}: ${e.msg}`).join("\n");
  }
  return "Error inesperado";
}
```

### Códigos de respuesta

| Código | Significado | Qué hacer en el cliente |
|---|---|---|
| 200 / 201 | Correcto | Usar la respuesta |
| 401 | Falta el token, no es válido o venció | Mandar al usuario al login |
| 403 | El rol del usuario no permite la acción, o está inactivo | Ocultar la opción o mostrar "sin permiso" |
| 404 | No existe, o el usuario no tiene acceso | Mostrar "no encontrado". La API no distingue los dos casos a propósito |
| 409 | Conflicto: espacio ocupado, solicitud duplicada, ya decidida o vencida | Mostrar `detail` y refrescar los datos |
| 422 | Datos inválidos | Mostrar `detail` junto al formulario |

---

## 3. Aviso: consumo desde un navegador (CORS)

**Hoy la API no tiene CORS habilitado.** Un frontend que corra en otro origen (por
ejemplo Angular en `http://localhost:4200`) no va a poder llamarla desde el navegador:
el navegador bloquea la petición antes de enviarla.

Desde curl, Postman, PowerShell, Swagger o un backend no hay problema.

Para habilitarlo hay que agregar `CORSMiddleware` en `app/main.py`, con la lista de
orígenes permitidos (por ejemplo `http://localhost:4200`). Hasta que eso se haga, una
alternativa en desarrollo es usar el proxy del servidor de desarrollo del frontend
(por ejemplo `proxy.conf.json` en Angular) para que las llamadas salgan del mismo origen.

---

## 4. Cliente mínimo en JavaScript

Este helper sirve para todos los ejemplos de la guía. Funciona con `fetch` en el
navegador o en Node 18+.

```js
const API = "http://localhost:8000/api/v1";
let token = null;

async function login(correo, clave) {
  const r = await fetch(`${API}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username: correo, password: clave }),
  });
  const cuerpo = await r.json();
  if (!r.ok) throw new Error(mensajeDeError(cuerpo));
  token = cuerpo.access_token;
  return cuerpo.usuario; // { id, nombre, email, rol, cargo }
}

async function api(metodo, ruta, datos) {
  const r = await fetch(`${API}${ruta}`, {
    method: metodo,
    headers: {
      ...(token && { Authorization: `Bearer ${token}` }),
      ...(datos && { "Content-Type": "application/json" }),
    },
    body: datos ? JSON.stringify(datos) : undefined,
  });
  const cuerpo = await r.json();
  if (!r.ok) {
    const error = new Error(mensajeDeError(cuerpo));
    error.status = r.status;
    throw error;
  }
  return cuerpo;
}
```

Uso:

```js
await login("estudiante@reservas.test", "Reservas2026*");
const espacios = await api("GET", "/espacios/");
```

## 5. Consumo desde PowerShell

En PowerShell `curl` es un alias de otro comando; usa `curl.exe` o `Invoke-RestMethod`.
Con `Invoke-RestMethod` es más fácil enviar JSON:

```powershell
$api = "http://localhost:8000/api/v1"

# Login (formulario)
$login = Invoke-RestMethod -Method Post -Uri "$api/auth/login" `
  -Body @{ username = "estudiante@reservas.test"; password = "Reservas2026*" }
$h = @{ Authorization = "Bearer $($login.access_token)" }

# GET con token
Invoke-RestMethod -Uri "$api/solicitudes/mias" -Headers $h

# POST con JSON
$cuerpo = @{ espacio_id = 2; fecha = "2026-10-05"; hora_inicio = "08:00"; hora_fin = "10:00";
             proposito = "Práctica"; asistentes = 15 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$api/solicitudes/" -Headers $h `
  -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($cuerpo))
```

Los ejemplos de curl de las secciones siguientes están escritos para bash o Git Bash.

---

## 6. Flujo completo de una reserva

```
SOLICITANTE                               APROBADOR
-----------                               ---------
1. POST /auth/login
2. GET  /espacios/disponibles             (elige espacio y horario)
3. GET  /espacios/{id}/disponibilidad     (opcional: confirma antes de enviar)
4. POST /solicitudes/            ──────►  5. POST /auth/login
                                          6. GET  /solicitudes/pendientes
                                          7. GET  /solicitudes/{id}
                                          8. POST /solicitudes/{id}/aprobar
                                             o    /solicitudes/{id}/rechazar
9. GET  /solicitudes/mias        ◄──────  (ve APROBADA, o RECHAZADA con motivo)
10. GET /reservas/mias                    (la reserva aparece si se aprobó)
11. GET /solicitudes/{id}/historial       (quién hizo qué y cuándo)
```

Estados de una solicitud:

```
PENDIENTE ──aprobar──► APROBADA  (se crea una reserva ACTIVA)
    │
    └────rechazar────► RECHAZADA (con motivo, sin reserva)
```

Una solicitud APROBADA o RECHAZADA ya no se puede volver a decidir.

---

## 7. Endpoints

Resumen:

| Método | Ruta | Rol | Sección |
|---|---|---|---|
| GET | `/` (fuera de `/api/v1`) | Público | 7.1 |
| POST | `/auth/login` | Público | 7.2 |
| GET | `/auth/me` | Cualquiera con sesión | 7.3 |
| GET | `/espacios/` | Público | 7.4 |
| POST | `/espacios/` | ADMIN | 7.4D |
| GET | `/espacios/admin` | ADMIN | 7.4A |
| PATCH | `/espacios/{espacio_id}` | ADMIN | 7.4B |
| PATCH | `/espacios/{espacio_id}/estado` | ADMIN | 7.4C |
| GET | `/espacios/disponibles` | Público | 7.5 |
| GET | `/espacios/{espacio_id}/disponibilidad` | Público | 7.6 |
| GET | `/espacios/metricas` | ADMIN | 7.6A |
| POST | `/solicitudes/` | SOLICITANTE | 7.7 |
| GET | `/solicitudes/mias` | SOLICITANTE | 7.8 |
| GET | `/solicitudes/pendientes` | APROBADOR o ADMIN | 7.9 |
| GET | `/solicitudes/resueltas` | APROBADOR o ADMIN | 7.9A |
| GET | `/solicitudes/{solicitud_id}` | Según el rol | 7.10 |
| POST | `/solicitudes/{solicitud_id}/aprobar` | APROBADOR | 7.11 |
| POST | `/solicitudes/{solicitud_id}/rechazar` | APROBADOR | 7.12 |
| GET | `/reservas/mias` | SOLICITANTE | 7.13 |
| POST | `/reservas/{reserva_id}/cancelar` | SOLICITANTE | 7.13A |
| GET | `/reservas/{reserva_id}` | Según el rol | 7.14 |
| GET | `/solicitudes/{solicitud_id}/historial` | Según el rol | 7.15 |
| GET | `/reservas/{reserva_id}/historial` | Según el rol | 7.16 |
| GET/POST | `/items/` | Público | 7.17 (ejemplo, no usar) |

Las rutas de la tabla van después de la URL base `http://localhost:8000/api/v1`.

"Según el rol" significa:
- SOLICITANTE: solo lo suyo.
- APROBADOR: solo lo de los espacios que administra.
- ADMIN: todo.

Si el usuario no tiene acceso, la respuesta es 404, igual que si no existiera.

En los ejemplos de curl, `$TOKEN` es el `access_token` obtenido en el login.

---

### 7.1 GET / — Estado de la API

Confirma que la API está en línea. Está fuera de `/api/v1` y no requiere token.

```bash
curl http://localhost:8000/
```

```json
{"message": "Bienvenido a la API de Reservas Laboratorios API"}
```

---

### 7.2 POST /auth/login — Iniciar sesión

Público. **Se envía como formulario, no como JSON.**

| Campo | Requerido | Descripción |
|---|---|---|
| `username` | Sí | Correo. No distingue mayúsculas |
| `password` | Sí | Clave |

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=estudiante@reservas.test" \
  -d "password=Reservas2026*"
```

```js
const usuario = await login("estudiante@reservas.test", "Reservas2026*");
```

Respuesta 200:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expira_en": 3600,
  "usuario": {
    "id": 4,
    "nombre": "Estudiante de Prueba",
    "email": "estudiante@reservas.test",
    "rol": "SOLICITANTE",
    "cargo": "ESTUDIANTE"
  }
}
```

Usa `usuario.rol` para decidir qué pantallas mostrar.

| Código | Cuándo |
|---|---|
| 401 | `"Correo o contraseña incorrectos"`. Es el mismo mensaje si el correo no existe |
| 403 | `"El usuario está inactivo"` |
| 422 | Falta `username` o `password`, o se envió como JSON |

Para guardar el token en una variable de bash:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=estudiante@reservas.test" -d "password=Reservas2026*" \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
```

---

### 7.3 GET /auth/me — Usuario actual

Cualquier usuario con sesión. Sirve para recuperar los datos del usuario al recargar
la página, o para comprobar si el token sigue siendo válido.

```bash
curl http://localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

```js
const yo = await api("GET", "/auth/me");
```

Respuesta 200:

```json
{"id": 4, "nombre": "Estudiante de Prueba", "email": "estudiante@reservas.test", "rol": "SOLICITANTE", "cargo": "ESTUDIANTE"}
```

| Código | Cuándo |
|---|---|
| 401 | `"No autenticado: el token falta, no es válido o expiró"`, o el usuario fue desactivado |

---

### 7.4 GET /espacios/ — Listar espacios

Público. Devuelve los laboratorios y salas **activos**, ordenados por tipo y nombre.

| Parámetro (query) | Requerido | Valores |
|---|---|---|
| `tipo` | No | `LABORATORIO` o `SALA`. Sin él trae ambos |

```bash
curl "http://localhost:8000/api/v1/espacios/?tipo=LABORATORIO"
```

```js
const laboratorios = await api("GET", "/espacios/?tipo=LABORATORIO");
```

Respuesta 200:

```json
[
  {"id": 2, "nombre": "Laboratorio de Electrónica", "tipo": "LABORATORIO", "capacidad": 20, "ubicacion": "Bloque A, piso 3"},
  {"id": 1, "nombre": "Laboratorio de Redes", "tipo": "LABORATORIO", "capacidad": 25, "ubicacion": "Bloque A, piso 2"},
  {"id": 3, "nombre": "Laboratorio de Software", "tipo": "LABORATORIO", "capacidad": 30, "ubicacion": "Bloque B, piso 1"}
]
```

| Código | Cuándo |
|---|---|
| 422 | `tipo` no es `LABORATORIO` ni `SALA` |

---

### 7.4A GET /espacios/admin — Listar espacios para administración

Rol **ADMIN**. Devuelve espacios activos e inactivos, ordenados por tipo y nombre.

```js
const espaciosAdmin = await api("GET", "/espacios/admin");
```

Cada espacio incluye `id`, `nombre`, `tipo`, `capacidad`, `ubicacion` y `activo`.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es ADMIN |

---

### 7.4D POST /espacios/ — Crear un espacio

Rol **ADMIN**. Cuerpo JSON:

| Campo | Requerido | Reglas |
|---|---|---|
| `nombre` | Sí | Único, hasta 120 caracteres; no puede ser solo espacios |
| `tipo` | Sí | `LABORATORIO` o `SALA` |
| `capacidad` | Sí | Entero mayor que 0 |
| `ubicacion` | No | Hasta 200 caracteres |

```js
const espacio = await api("POST", "/espacios/", {
  nombre: "Laboratorio de Redes", tipo: "LABORATORIO", capacidad: 25, ubicacion: "Bloque A, piso 2",
});
```

Respuesta **201**: el espacio con su `id` y `activo: true`, igual que en `/espacios/admin`.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es ADMIN |
| 409 | Ya existe un espacio con ese nombre |
| 422 | Datos inválidos o campos no permitidos |

---

### 7.4B PATCH /espacios/{espacio_id} — Editar un espacio

Rol **ADMIN**. Actualiza solo los campos enviados: `nombre`, `tipo`, `capacidad` y `ubicacion`.
Se permite enviar `ubicacion: null` para quitarla. El cuerpo no puede estar vacío.

```json
{"nombre": "Laboratorio de Redes", "capacidad": 28, "ubicacion": "Bloque B, piso 2"}
```

No se puede reducir la capacidad por debajo de los asistentes de una reserva futura ACTIVA
(409). Las solicitudes PENDIENTES permanecen, pero no podrán aprobarse si exceden la capacidad
nueva.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es ADMIN |
| 404 | El espacio no existe |
| 409 | Nombre duplicado o capacidad menor a la de una reserva futura |
| 422 | Campos inválidos o cuerpo vacío |

---

### 7.4C PATCH /espacios/{espacio_id}/estado — Activar o desactivar

Rol **ADMIN**. Cuerpo: `{"activo": false}` para desactivar o `{"activo": true}` para reactivar.
La desactivación conserva las reservas futuras aprobadas y el historial, pero bloquea nuevas
solicitudes y aprobaciones. No se borra físicamente el espacio porque hay referencias desde
solicitudes y reservas.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es ADMIN |
| 404 | El espacio no existe |
| 422 | Falta `activo` o tiene un valor inválido |

---

### 7.5 GET /espacios/disponibles — Espacios libres en un horario

Público. Devuelve los espacios activos que **no** tienen una reserva activa que se
cruce con el horario pedido.

| Parámetro (query) | Requerido | Formato |
|---|---|---|
| `fecha` | Sí | `AAAA-MM-DD` |
| `hora_inicio` | Sí | `HH:MM` |
| `hora_fin` | Sí | `HH:MM` |
| `tipo` | No | `LABORATORIO` o `SALA` |

Reglas:
- Una reserva que se cruza, aunque sea parcialmente, deja el espacio fuera.
- Una reserva que termina justo cuando empieza la consulta no bloquea (08:00-10:00
  no bloquea 10:00-12:00).
- Las solicitudes pendientes **no** bloquean: solo las reservas ya aprobadas.
- Si no hay espacios libres, la respuesta es 200 con `[]`.

```bash
curl "http://localhost:8000/api/v1/espacios/disponibles?fecha=2026-10-05&hora_inicio=08:00&hora_fin=10:00&tipo=LABORATORIO"
```

```js
const params = new URLSearchParams({ fecha: "2026-10-05", hora_inicio: "08:00", hora_fin: "10:00" });
const libres = await api("GET", `/espacios/disponibles?${params}`);
```

La respuesta tiene el mismo formato que `GET /espacios/`.

| Código | Cuándo |
|---|---|
| 422 | Falta un parámetro, la hora de fin no es mayor que la de inicio, o la fecha y hora ya pasaron |

---

### 7.6 GET /espacios/{espacio_id}/disponibilidad — ¿Está libre este espacio?

Público. Sirve para avisar al usuario **antes** de enviar la solicitud. Es solo
informativo: al crear la solicitud la API vuelve a validar.

| Parámetro | Dónde | Requerido |
|---|---|---|
| `espacio_id` | Ruta | Sí |
| `fecha` | Query | Sí |
| `hora_inicio` | Query | Sí |
| `hora_fin` | Query | Sí |

```bash
curl "http://localhost:8000/api/v1/espacios/1/disponibilidad?fecha=2026-10-05&hora_inicio=08:00&hora_fin=10:00"
```

```js
const r = await api("GET", `/espacios/1/disponibilidad?${params}`);
if (!r.disponible) alert(r.mensaje);
```

Respuesta 200 (siempre 200, esté libre o no):

```json
{"espacio_id": 1, "disponible": false, "mensaje": "El espacio ya se encuentra ocupado en ese horario"}
```

```json
{"espacio_id": 1, "disponible": true, "mensaje": "El espacio está disponible en ese horario"}
```

| Código | Cuándo |
|---|---|
| 404 | El espacio no existe o no está activo |
| 422 | Horario inválido o en el pasado |

---

### 7.6A GET /espacios/metricas — Métricas de ocupación por espacio

Rol **ADMIN**. Devuelve las métricas de todos los espacios (activos e inactivos) para la fecha
consultada, evitando una petición por cada espacio.

| Parámetro (query) | Requerido | Formato |
|---|---|---|
| `fecha` | Sí | `AAAA-MM-DD` |

Las reservas CANCELADAS no cuentan. `reservas_dia` cuenta las reservas ACTIVAS que se cruzan
con la fecha. `minutos_reservados` cuenta solo el tiempo dentro del horario institucional,
de 07:00 a 22:00 (hora de Colombia), todos los días: un espacio activo tiene 900 minutos
disponibles por día. Para espacios inactivos, los minutos disponibles son 0 y
`porcentaje_ocupacion` es `null`.

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/espacios/metricas?fecha=2026-10-06"
```

```js
const metricas = await api("GET", "/espacios/metricas?fecha=2026-10-06");
```

Respuesta 200:

```json
[
  {
    "id": 1,
    "nombre": "Laboratorio de Redes",
    "tipo": "LABORATORIO",
    "capacidad": 25,
    "ubicacion": "Bloque A, piso 2",
    "activo": true,
    "fecha": "2026-10-06",
    "reservas_dia": 2,
    "minutos_reservados": 90,
    "minutos_disponibles": 900,
    "porcentaje_ocupacion": 10
  }
]
```

| Código | Cuándo |
|---|---|
| 401 | Falta el token, no es válido o expiró |
| 403 | El rol no es ADMIN |
| 422 | La fecha no tiene formato válido |

---

### 7.7 POST /solicitudes/ — Crear solicitud de reserva

Rol **SOLICITANTE**. Registra la solicitud en estado PENDIENTE. Cuerpo JSON:

| Campo | Requerido | Reglas |
|---|---|---|
| `espacio_id` | Sí | Espacio activo |
| `fecha` | Sí | `AAAA-MM-DD` |
| `hora_inicio` | Sí | `HH:MM`, desde las 07:00, no en el pasado |
| `hora_fin` | Sí | `HH:MM`, mayor que `hora_inicio`, hasta las 22:00 |
| `proposito` | Sí | 1 a 500 caracteres; no puede ser solo espacios |
| `asistentes` | Sí | Mayor que 0 y no mayor que la capacidad del espacio |
| `equipamiento` | No | Hasta 500 caracteres |

```bash
curl -X POST http://localhost:8000/api/v1/solicitudes/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"espacio_id": 2, "fecha": "2026-10-05", "hora_inicio": "08:00", "hora_fin": "10:00", "proposito": "Práctica de circuitos", "asistentes": 15, "equipamiento": "Proyector"}'
```

```js
const solicitud = await api("POST", "/solicitudes/", {
  espacio_id: 2,
  fecha: "2026-10-05",
  hora_inicio: "08:00",
  hora_fin: "10:00",
  proposito: "Práctica de circuitos",
  asistentes: 15,
  equipamiento: "Proyector",
});
alert(solicitud.mensaje);
```

Respuesta **201**:

```json
{
  "id": 2,
  "espacio_id": 2,
  "espacio_nombre": "Laboratorio de Electrónica",
  "inicio": "2026-10-05T08:00:00-05:00",
  "fin": "2026-10-05T10:00:00-05:00",
  "proposito": "Práctica de circuitos",
  "asistentes": 15,
  "equipamiento": "Proyector",
  "estado": "PENDIENTE",
  "motivo_rechazo": null,
  "fecha_decision": null,
  "creada_en": "2026-09-22T22:12:44.490045-05:00",
  "mensaje": "Solicitud #2 registrada. Quedó en estado PENDIENTE."
}
```

| Código | `detail` | Cuándo |
|---|---|---|
| 401 | No autenticado… | Sin token |
| 403 | No tienes permiso para esta acción | El usuario no es SOLICITANTE |
| 404 | El espacio no existe o no está activo | |
| 409 | El espacio ya está ocupado en ese horario | Hay una reserva aprobada que se cruza |
| 409 | Ya tienes una solicitud pendiente (#N) para ese espacio en un horario que se cruza | Evita duplicados, por ejemplo por doble clic |
| 422 | La hora de fin debe ser mayor que la hora de inicio | |
| 422 | No se puede solicitar un espacio en una fecha u hora pasada | |
| 422 | La cantidad de asistentes (21) supera la capacidad del espacio (20) | |
| 422 | Lista de errores de FastAPI | Falta un campo, `proposito` vacío o `asistentes` en 0 |

Una solicitud pendiente de **otro** usuario no bloquea: pueden existir varias
pendientes para el mismo horario, y el aprobador decide cuál aprobar.

---

### 7.8 GET /solicitudes/mias — Mis solicitudes

Rol **SOLICITANTE**. Devuelve las solicitudes del usuario, de la más reciente a la
más antigua. Aquí el solicitante ve si su solicitud fue aprobada o rechazada, y el
motivo del rechazo.

| Parámetro (query) | Requerido | Valores |
|---|---|---|
| `estado` | No | `PENDIENTE`, `APROBADA`, `RECHAZADA` o `CANCELADA` |

```bash
curl "http://localhost:8000/api/v1/solicitudes/mias?estado=RECHAZADA" -H "Authorization: Bearer $TOKEN"
```

```js
const mias = await api("GET", "/solicitudes/mias");
```

Respuesta 200: una lista con el mismo formato de la respuesta de 7.7, sin el campo
`mensaje`. Ejemplo de una rechazada:

```json
[
  {
    "id": 3,
    "espacio_id": 2,
    "espacio_nombre": "Laboratorio de Electrónica",
    "inicio": "2026-10-05T08:00:00-05:00",
    "fin": "2026-10-05T10:00:00-05:00",
    "proposito": "Práctica",
    "asistentes": 15,
    "equipamiento": null,
    "estado": "RECHAZADA",
    "motivo_rechazo": "El laboratorio ya fue asignado a otra práctica",
    "fecha_decision": "2026-09-22T22:31:50.102030-05:00",
    "creada_en": "2026-09-22T22:12:44.702215-05:00"
  }
]
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es SOLICITANTE |

---

### 7.9 GET /solicitudes/pendientes — Bandeja del aprobador

Roles **APROBADOR** y **ADMIN**. El APROBADOR ve las solicitudes PENDIENTE de los espacios
que administra; el ADMIN las de todos los espacios, solo en consulta (no puede aprobar ni
rechazar). Se ordenan por hora de inicio (las más próximas primero).

| Parámetro (query) | Requerido | Descripción |
|---|---|---|
| `espacio_id` | No | Filtra por un espacio. Si no lo administra, devuelve `[]` |

```bash
curl http://localhost:8000/api/v1/solicitudes/pendientes -H "Authorization: Bearer $TOKEN"
```

```js
const bandeja = await api("GET", "/solicitudes/pendientes");
```

Respuesta 200:

```json
[
  {
    "id": 4,
    "estado": "PENDIENTE",
    "solicitante": {"id": 4, "nombre": "Estudiante de Prueba", "email": "estudiante@reservas.test", "cargo": "ESTUDIANTE"},
    "espacio": {"id": 1, "nombre": "Laboratorio de Redes", "tipo": "LABORATORIO", "capacidad": 25, "ubicacion": "Bloque A, piso 2"},
    "inicio": "2026-10-05T10:00:00-05:00",
    "fin": "2026-10-05T12:00:00-05:00",
    "asistentes": 15,
    "creada_en": "2026-09-22T22:12:44.590112-05:00",
    "vencida": false
  }
]
```

`vencida: true` significa que la hora de inicio ya pasó. Esa solicitud ya no se puede
aprobar, solo rechazar. Conviene deshabilitar el botón "Aprobar" en ese caso.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es APROBADOR (un ADMIN también recibe 403) |

---

### 7.9A GET /solicitudes/resueltas — Historial de solicitudes por espacio

Roles **APROBADOR** y **ADMIN**. Devuelve las solicitudes APROBADAS y RECHAZADAS de un espacio,
ordenadas por fecha de resolución descendente. El APROBADOR solo ve los espacios que administra
(uno no asignado devuelve `[]`). El ADMIN ve cualquier espacio, pero solo en consulta: aprobar y
rechazar siguen siendo exclusivos del APROBADOR.

| Parámetro (query) | Requerido | Descripción |
|---|---|---|
| `espacio_id` | Sí | Identificador positivo del espacio |
| `estado` | No | `APROBADA` o `RECHAZADA` |
| `fecha_desde` | No | Fecha inicial de resolución, inclusiva (`AAAA-MM-DD`) |
| `fecha_hasta` | No | Fecha final de resolución, inclusiva (`AAAA-MM-DD`) |

El rango de fechas se interpreta en hora de Colombia. Las solicitudes PENDIENTES y CANCELADAS
no aparecen.

```bash
curl "http://localhost:8000/api/v1/solicitudes/resueltas?espacio_id=1&estado=RECHAZADA" \
  -H "Authorization: ******"
```

```js
const params = new URLSearchParams({ espacio_id: "1", estado: "RECHAZADA" });
const historial = await api("GET", `/solicitudes/resueltas?${params}`);
```

Respuesta 200:

```json
[
  {
    "id": 8,
    "estado": "RECHAZADA",
    "solicitante": {"id": 4, "nombre": "Estudiante de Prueba", "email": "estudiante@reservas.test", "cargo": "ESTUDIANTE"},
    "espacio": {"id": 1, "nombre": "Laboratorio de Redes", "tipo": "LABORATORIO", "capacidad": 25, "ubicacion": "Bloque A, piso 2"},
    "inicio": "2026-10-08T10:00:00-05:00",
    "fin": "2026-10-08T12:00:00-05:00",
    "asistentes": 15,
    "decidida_por": "Coordinador de Laboratorios",
    "fecha_decision": "2026-10-06T09:15:00-05:00",
    "motivo_rechazo": "No hay disponibilidad"
  }
]
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es APROBADOR |
| 422 | Filtro inválido o `fecha_desde` posterior a `fecha_hasta` |

---

### 7.10 GET /solicitudes/{solicitud_id} — Detalle de una solicitud

Cualquier rol, según el acceso (ver la sección 7). Devuelve lo mismo que la bandeja,
más los campos de la decisión.

```bash
curl http://localhost:8000/api/v1/solicitudes/2 -H "Authorization: Bearer $TOKEN"
```

```js
const detalle = await api("GET", `/solicitudes/${id}`);
```

Respuesta 200 (los campos de la bandeja más estos):

```json
{
  "...": "id, estado, solicitante, espacio, inicio, fin, asistentes, creada_en, vencida",
  "proposito": "Práctica",
  "equipamiento": null,
  "motivo_rechazo": null,
  "decidido_por": "Coordinador de Laboratorios",
  "fecha_decision": "2026-09-22T22:31:49.561237-05:00"
}
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 404 | `"La solicitud no existe o no tienes acceso a ella"` |
| 422 | El id no es un número |

---

### 7.11 POST /solicitudes/{solicitud_id}/aprobar — Aprobar

Rol **APROBADOR**, solo en espacios que administra. **No lleva cuerpo.** En una sola
operación aprueba la solicitud y crea la reserva ACTIVA a nombre del solicitante.

```bash
curl -X POST http://localhost:8000/api/v1/solicitudes/2/aprobar -H "Authorization: Bearer $TOKEN"
```

```js
const r = await api("POST", `/solicitudes/${id}/aprobar`);
alert(r.mensaje);
```

Respuesta 200:

```json
{
  "mensaje": "Solicitud #2 aprobada. Se generó la reserva #2.",
  "solicitud": {"...": "el detalle completo de 7.10, con estado APROBADA"},
  "reserva": {
    "id": 2,
    "solicitud_id": 2,
    "espacio_id": 2,
    "espacio_nombre": "Laboratorio de Electrónica",
    "inicio": "2026-10-05T08:00:00-05:00",
    "fin": "2026-10-05T10:00:00-05:00",
    "estado": "ACTIVA"
  }
}
```

| Código | `detail` |
|---|---|
| 401 | No autenticado… |
| 403 | No tienes permiso para esta acción (no es APROBADOR) |
| 404 | La solicitud no existe o no tienes acceso a ella (o es de un espacio que no administra) |
| 409 | La solicitud ya no está pendiente (estado actual: APROBADA) |
| 409 | La solicitud está vencida: su hora de inicio ya pasó. Solo se puede rechazar |
| 409 | El espacio ya no está activo. Solo se puede rechazar |
| 409 | Los asistentes superan la capacidad actual del espacio |
| 409 | El espacio ya fue reservado en ese horario por otra solicitud aprobada |

Si llegan dos aprobaciones al mismo tiempo (dos aprobadores, o un doble clic), solo
una pasa y la otra recibe 409. Al recibir 409, refresca la bandeja.

---

### 7.12 POST /solicitudes/{solicitud_id}/rechazar — Rechazar con motivo

Rol **APROBADOR**, solo en espacios que administra. El motivo es obligatorio. Se
puede rechazar aunque la solicitud esté vencida. Un rechazo nunca crea reserva.

| Campo (JSON) | Requerido | Reglas |
|---|---|---|
| `motivo` | Sí | 1 a 500 caracteres; no puede ser solo espacios |

```bash
curl -X POST http://localhost:8000/api/v1/solicitudes/3/rechazar \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"motivo": "El laboratorio ya fue asignado a otra práctica"}'
```

```js
const r = await api("POST", `/solicitudes/${id}/rechazar`, { motivo });
```

Respuesta 200:

```json
{
  "mensaje": "Solicitud #3 rechazada.",
  "solicitud": {"...": "el detalle completo de 7.10, con estado RECHAZADA y motivo_rechazo"}
}
```

| Código | Cuándo |
|---|---|
| 401, 403, 404 | Igual que en aprobar |
| 409 | La solicitud ya no está pendiente |
| 422 | Falta `motivo` o está vacío |

---

### 7.13 GET /reservas/mias — Mis reservas activas

Rol **SOLICITANTE**. Devuelve las reservas ACTIVAS del usuario que todavía no han
terminado, ordenadas por fecha y hora de inicio. Las que ya pasaron nunca aparecen.

Con `?incluir_canceladas=true` también salen las CANCELADAS (con `estado: "CANCELADA"`),
para mostrarlas atenuadas en el dashboard sin que desaparezcan al recargar.

```bash
curl http://localhost:8000/api/v1/reservas/mias -H "Authorization: Bearer $TOKEN"
```

```js
const reservas = await api("GET", "/reservas/mias");
```

Respuesta 200:

```json
[
  {
    "id": 2,
    "estado": "ACTIVA",
    "espacio": {"id": 2, "nombre": "Laboratorio de Electrónica", "tipo": "LABORATORIO", "capacidad": 20, "ubicacion": "Bloque A, piso 3"},
    "inicio": "2026-10-05T08:00:00-05:00",
    "fin": "2026-10-05T10:00:00-05:00",
    "solicitud_id": 2
  }
]
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es SOLICITANTE |

---

### 7.13A POST /reservas/{reserva_id}/cancelar — Cancelar una reserva

Rol **SOLICITANTE**. Solo se pueden cancelar las reservas propias que todavía no hayan
comenzado. La operación también cambia a CANCELADA la solicitud asociada y registra el
cambio en el historial. Repetir la petición de una reserva ya cancelada devuelve éxito sin
duplicar el registro del historial.

```bash
curl -X POST http://localhost:8000/api/v1/reservas/2/cancelar \
  -H "Authorization: ******"
```

```js
const cancelada = await api("POST", `/reservas/${id}/cancelar`);
```

Respuesta 200:

```json
{
  "id": 2,
  "estado": "CANCELADA",
  "espacio": {"id": 2, "nombre": "Laboratorio de Electrónica", "tipo": "LABORATORIO", "capacidad": 20, "ubicacion": "Bloque A, piso 3"},
  "inicio": "2026-10-05T08:00:00-05:00",
  "fin": "2026-10-05T10:00:00-05:00",
  "solicitud_id": 2
}
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 403 | El usuario no es SOLICITANTE |
| 404 | La reserva no existe o no pertenece al usuario |
| 409 | La reserva ya inició |

---

### 7.14 GET /reservas/{reserva_id} — Detalle de una reserva

Cualquier rol, según el acceso (ver la sección 7). También muestra reservas
canceladas o ya terminadas.

```bash
curl http://localhost:8000/api/v1/reservas/2 -H "Authorization: Bearer $TOKEN"
```

Respuesta 200 (los campos de 7.13 más estos):

```json
{
  "...": "id, estado, espacio, inicio, fin, solicitud_id",
  "finalizada": false,
  "titular": "Estudiante de Prueba",
  "proposito": "Práctica",
  "asistentes": 15,
  "equipamiento": null,
  "aprobada_por": "Coordinador de Laboratorios",
  "fecha_aprobacion": "2026-09-22T22:31:49.561237-05:00",
  "creada_en": "2026-09-22T22:31:49.557113-05:00"
}
```

`finalizada: true` significa que la hora de fin ya pasó.

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 404 | `"La reserva no existe o no tienes acceso a ella"` |
| 422 | El id no es un número |

---

### 7.15 GET /solicitudes/{solicitud_id}/historial — Historial de una solicitud

Cualquier rol, según el acceso (ver la sección 7). Devuelve cada acción registrada
sobre la solicitud, en orden cronológico. El historial no se puede modificar ni borrar.

```bash
curl http://localhost:8000/api/v1/solicitudes/2/historial -H "Authorization: Bearer $TOKEN"
```

```js
const { acciones } = await api("GET", `/solicitudes/${id}/historial`);
```

Respuesta 200:

```json
{
  "solicitud_id": 2,
  "reserva_id": 2,
  "acciones": [
    {
      "orden": 1,
      "accion": "CREADA",
      "usuario_id": 4,
      "usuario_nombre": "Estudiante de Prueba",
      "usuario_rol": "SOLICITANTE",
      "estado_anterior": null,
      "estado_nuevo": "PENDIENTE",
      "detalle": null,
      "reserva_id": null,
      "fecha": "2026-09-22T22:12:44.490045-05:00"
    },
    {
      "orden": 2,
      "accion": "APROBADA",
      "usuario_id": 2,
      "usuario_nombre": "Coordinador de Laboratorios",
      "usuario_rol": "APROBADOR",
      "estado_anterior": "PENDIENTE",
      "estado_nuevo": "APROBADA",
      "detalle": "Reserva #2 generada",
      "reserva_id": 2,
      "fecha": "2026-09-22T22:31:49.575660-05:00"
    }
  ]
}
```

En un rechazo, `detalle` trae el motivo. `reserva_id` es `null` si la solicitud no
se aprobó. La solicitud #1 de los datos de prueba se crea directo en la base, así que
su historial viene vacío (`"acciones": []`).

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 404 | `"La solicitud no existe o no tienes acceso a ella"` |
| 422 | El id no es un número |

---

### 7.16 GET /reservas/{reserva_id}/historial — Historial de una reserva

Mismo formato que 7.15. Devuelve el historial de la solicitud que generó la reserva.

```bash
curl http://localhost:8000/api/v1/reservas/2/historial -H "Authorization: Bearer $TOKEN"
```

| Código | Cuándo |
|---|---|
| 401 | Sin token |
| 404 | `"La reserva no existe o no tienes acceso a ella"` |
| 422 | El id no es un número |

---

### 7.17 /items/ — Recurso de ejemplo (no usar)

`GET /items/`, `GET /items/{item_id}` y `POST /items/` son el ejemplo con el que se
creó el proyecto. Guardan los datos en memoria (se pierden al reiniciar la API) y
no son parte del sistema de reservas. `GET /items/{item_id}` con un id que no existe
responde 500 en lugar de 404. No los uses desde el frontend.

---

## 8. Recetas rápidas para el frontend

**Formulario de solicitud:**
1. Cargar espacios con `GET /espacios/` para el selector.
2. Al elegir espacio, fecha y horas, llamar a `GET /espacios/{id}/disponibilidad`
   y mostrar `mensaje` si `disponible` es `false`.
3. Validar en el cliente que `asistentes` no supere `capacidad` del espacio elegido.
4. Enviar con `POST /solicitudes/`. Deshabilitar el botón mientras la petición está
   en curso; si igual llega un 409 por duplicado, mostrar `detail`.

**Bandeja del aprobador:**
1. `GET /solicitudes/pendientes`.
2. Al abrir una: `GET /solicitudes/{id}`.
3. Botón "Aprobar" deshabilitado si `vencida` es `true`.
4. "Rechazar" abre un campo obligatorio para el motivo.
5. Después de aprobar o rechazar, o si llega un 409, volver a cargar la bandeja.

**Mis reservas:**
1. `GET /reservas/mias` para la lista.
2. `GET /reservas/{id}` para el detalle.
3. `GET /reservas/{id}/historial` para la línea de tiempo.

**Sesión:**
1. Guardar el token después del login.
2. Al recargar la página, llamar a `GET /auth/me`. Si responde 401, volver al login.
3. Ante cualquier 401 en otra llamada, borrar el token y volver al login.
