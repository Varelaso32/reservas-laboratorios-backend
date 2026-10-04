# Fase: gestión de usuarios

Complementa `docs/API.md`, con las mismas convenciones: rutas bajo `/api/v1`, errores de negocio
`{"detail": "mensaje"}`, errores de formato `{"detail": [lista por campo]}` (textos en inglés,
generados por FastAPI), token JWT en `Authorization: Bearer <token>` obtenido con
`POST /api/v1/auth/login`.

Swagger: http://localhost:8000/docs, sección **Usuarios**.

## Resumen

| Método | Ruta | Resumen | Rol |
|---|---|---|---|
| POST | /api/v1/usuarios/ | Crear usuario | ADMIN |
| GET | /api/v1/usuarios/ | Listar usuarios (paginado, filtros) | ADMIN |
| GET | /api/v1/usuarios/{usuario_id} | Consultar un usuario | ADMIN (cualquiera), los demás (solo a sí mismos) |
| PATCH | /api/v1/usuarios/{usuario_id} | Actualizar nombre, correo, rol o cargo | ADMIN |
| PATCH | /api/v1/usuarios/{usuario_id}/estado | Activar o desactivar (borrado lógico) | ADMIN |
| POST | /api/v1/auth/registro | Auto-registro desde el login (queda como estudiante) | Público |

Hay dos formas de crear usuarios: el ADMIN crea cualquiera con `POST /usuarios/` (eligiendo rol y
cargo), o la persona se registra sola con `POST /auth/registro` y queda siempre como estudiante.

Para los datos del usuario con sesión ya existe `GET /api/v1/auth/me` (fase 2); no se duplicó.

## Reglas comunes

- **Correo:** se guarda con `strip()` y en minúsculas. Debe tener un solo `@`, texto antes y
  después, al menos un punto en el dominio, sin espacios y máximo 254 caracteres. Se aceptan
  dominios `.test` (los usuarios de prueba los usan). Es único sin importar mayúsculas: lo
  garantiza el índice `ux_usuario_email_lower` de la BD, también ante dos peticiones simultáneas.
- **Clave:** de 8 a 128 caracteres. Se guarda solo el hash Argon2 (`app/core/security.py`).
  No se trunca: Argon2 no tiene el límite de 72 bytes de bcrypt. La clave y el hash no aparecen
  en ninguna respuesta ni en el esquema de Swagger.
- **Nombre:** se le quitan los espacios de los extremos; no puede quedar vacío; máximo 120.
- **Rol y cargo:** el cargo es opcional, pero si se envía debe corresponder al rol.

  | Rol | Cargos válidos |
  |---|---|
  | SOLICITANTE | ESTUDIANTE, DOCENTE, ADMINISTRATIVO |
  | APROBADOR | COORDINADOR_LABORATORIOS, ADMINISTRADOR_SALA |
  | ADMIN | ADMINISTRADOR_SISTEMA |

- **Campos extra:** los cuerpos rechazan campos no definidos (`id`, `clave_hash`, `activo` en la
  creación, etc.) con 422.
- **Último ADMIN:** no se puede desactivar ni quitar el rol al único ADMIN activo (400).
- El rol del sistema se llama `ADMIN` (no `ADMINISTRADOR`), igual que en el resto de la API.

## POST /api/v1/usuarios/

Crea un usuario. Nace activo.

**Rol:** ADMIN.

Request:

```json
{
  "nombre": "Laura Gómez",
  "email": "laura.gomez@ecci.edu.co",
  "clave": "Laboratorio2026*",
  "rol": "SOLICITANTE",
  "cargo": "ESTUDIANTE"
}
```

Respuesta 201:

```json
{
  "id": 7,
  "nombre": "Laura Gómez",
  "email": "laura.gomez@ecci.edu.co",
  "rol": "SOLICITANTE",
  "cargo": "ESTUDIANTE",
  "activo": true,
  "creado_en": "2026-10-02T09:15:00-05:00"
}
```

| Código | Cuándo | Ejemplo |
|---|---|---|
| 400 | El cargo no corresponde al rol | `{"detail": "El cargo COORDINADOR_LABORATORIOS no corresponde al rol SOLICITANTE. Cargos válidos: ADMINISTRATIVO, DOCENTE, ESTUDIANTE"}` |
| 401 | Sin token o token inválido | `{"detail": "No autenticado: el token falta, no es válido o expiró"}` |
| 403 | El usuario no es ADMIN | `{"detail": "No tienes permiso para esta acción"}` |
| 409 | Correo ya registrado (también `" JUAN@x.com"` vs `"juan@x.com"`) | `{"detail": "Ya existe un usuario con ese correo"}` |
| 422 | Campo faltante, correo mal formado, clave fuera de 8–128, rol inexistente, campo extra | `{"detail": [...]}` |

## GET /api/v1/usuarios/

Lista usuarios ordenados por id.

**Rol:** ADMIN.

Parámetros de consulta:

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| skip | int ≥ 0 | 0 | Registros a saltar |
| limit | int 1–100 | 20 | Máximo de registros |
| rol | SOLICITANTE / APROBADOR / ADMIN | — | Filtro opcional |
| activo | bool | — | `true` solo activos, `false` solo inactivos; sin enviar, todos |

Ejemplo: `GET /api/v1/usuarios/?rol=SOLICITANTE&activo=true&skip=0&limit=20`

Respuesta 200:

```json
{
  "total": 3,
  "skip": 0,
  "limit": 20,
  "items": [
    {
      "id": 4,
      "nombre": "Estudiante de Prueba",
      "email": "estudiante@reservas.test",
      "rol": "SOLICITANTE",
      "cargo": "ESTUDIANTE",
      "activo": true,
      "creado_en": "2026-09-22T20:45:00-05:00"
    }
  ]
}
```

`total` cuenta todos los que cumplen el filtro, no solo los de la página.

| Código | Cuándo |
|---|---|
| 401 | Sin token o token inválido |
| 403 | El usuario no es ADMIN |
| 422 | `skip` negativo, `limit` fuera de 1–100, o `rol` inexistente |

## GET /api/v1/usuarios/{usuario_id}

Devuelve un usuario.

**Rol:** ADMIN puede consultar a cualquiera. Los demás roles, solo a sí mismos.

Respuesta 200: igual a la de creación.

| Código | Cuándo | Ejemplo |
|---|---|---|
| 401 | Sin token o token inválido | |
| 404 | El id no existe, **o** un no ADMIN pide un id que no es el suyo | `{"detail": "El usuario no existe"}` |
| 422 | El id no es un número | |

Nota: el 404 a un no ADMIN es intencional (no 403). La respuesta es idéntica exista o no el id,
para no revelar qué ids están registrados.

## PATCH /api/v1/usuarios/{usuario_id}

Cambia los datos básicos y el rol. Solo se modifican los campos enviados.

**Rol:** ADMIN.

Request (todos opcionales):

```json
{
  "nombre": "Laura Gómez Ruiz",
  "email": "lgomez@ecci.edu.co",
  "rol": "APROBADOR",
  "cargo": "COORDINADOR_LABORATORIOS"
}
```

Respuesta 200: el usuario actualizado (misma forma que en la creación).

| Código | Cuándo |
|---|---|
| 400 | El cargo final no corresponde al rol final, o se intenta quitar el rol al único ADMIN activo |
| 401 | Sin token o token inválido |
| 403 | El usuario no es ADMIN |
| 404 | El usuario no existe |
| 409 | El correo nuevo ya lo usa otro usuario |
| 422 | Formato inválido, `null` en `nombre`, `email` o `rol`, o un campo no permitido (por ejemplo `clave` o `activo`) |

Notas:

- Se valida el estado **final**. Si solo se envía `rol`, el cargo actual también debe encajar con
  el nuevo rol. Por ejemplo, para pasar un ESTUDIANTE a APROBADOR hay que enviar
  `{"rol": "APROBADOR", "cargo": "COORDINADOR_LABORATORIOS"}` o `{"rol": "APROBADOR", "cargo": null}`.
- `cargo` sí acepta `null` (lo quita).
- La clave y el estado no se cambian aquí.

## PATCH /api/v1/usuarios/{usuario_id}/estado

Activa o desactiva un usuario. Es un borrado lógico: la fila no se elimina porque solicitudes,
reservas e historial la referencian.

**Rol:** ADMIN.

Request:

```json
{ "activo": false }
```

Respuesta 200: el usuario con `"activo": false`.

| Código | Cuándo |
|---|---|
| 400 | Se intenta desactivar al único ADMIN activo |
| 401 | Sin token o token inválido |
| 403 | El usuario no es ADMIN |
| 404 | El usuario no existe |
| 422 | Falta `activo` o no es booleano |

Efecto de desactivar:

- Sus tokens dejan de servir de inmediato (401), porque `get_usuario_actual` revisa `activo` en
  cada petición.
- El login le responde 403 "El usuario está inactivo".
- Sus solicitudes, reservas e historial se conservan.

## POST /api/v1/auth/registro

Auto-registro desde la pantalla de inicio de sesión. Ahorra que el ADMIN tenga que crear a cada
estudiante.

**Rol:** público (no requiere token; si se envía uno, se ignora).

Request (solo estos tres campos):

```json
{
  "nombre": "Laura Gómez",
  "email": "laura.gomez@ecci.edu.co",
  "clave": "Laboratorio2026*"
}
```

Respuesta 201 (no incluye token):

```json
{
  "id": 8,
  "nombre": "Laura Gómez",
  "email": "laura.gomez@ecci.edu.co",
  "rol": "SOLICITANTE",
  "cargo": "ESTUDIANTE",
  "activo": true,
  "creado_en": "2026-10-03T10:20:00-05:00"
}
```

| Código | Cuándo | Ejemplo |
|---|---|---|
| 400 | El correo no es de un dominio permitido | `{"detail": "Solo se pueden registrar correos institucionales (@ecci.edu.co, @reservas.test)"}` |
| 409 | El correo ya está registrado (por registro o porque lo creó un ADMIN) | `{"detail": "Ya existe un usuario con ese correo"}` |
| 422 | Campo faltante, correo mal formado, clave fuera de 8–128, o se envió `rol`, `cargo`, `activo` u otro campo | `{"detail": [...]}` |

Notas:

- La cuenta queda **siempre** con rol SOLICITANTE y cargo ESTUDIANTE. El rol no se toma de la
  petición: si el front manda `rol` (por ejemplo para intentar ser ADMIN), responde 422 y no se crea
  nada.
- **Dominios permitidos:** solo coincidencia exacta. `@ecci.edu.co` y `@reservas.test` entran;
  `@gmail.com`, `@est.ecci.edu.co` o `@ecci.edu.co.otro.com` no. Se configuran con la variable de
  entorno del sistema `REGISTRO_DOMINIOS` (separados por coma; por defecto
  `ecci.edu.co,reservas.test`). En producción conviene dejar solo `ecci.edu.co`.
- **No inicia sesión.** Después del 201 el front debe mandar al usuario al login
  (`POST /api/v1/auth/login`).
- Si quien se registró es docente o administrativo, un ADMIN le corrige el cargo con
  `PATCH /api/v1/usuarios/{usuario_id}` (por ejemplo `{"cargo": "DOCENTE"}`).
- El 409 permite saber si un correo ya está registrado. Es lo normal en un formulario de registro y
  se acepta.

## Primer ADMIN (arranque)

`POST /api/v1/usuarios/` exige ser ADMIN, así que el primero se crea con un script:

```
docker compose exec -e ADMIN_EMAIL=admin@ecci.edu.co -e ADMIN_NOMBRE="Administrador del Sistema" -e ADMIN_CLAVE='UnaClaveSegura2026*' api python -m app.utils.crear_admin
```

- Las variables van en el comando y no en el `.env`, porque `config.py` rechaza variables que no
  tiene declaradas.
- Aplica las mismas validaciones que la API (correo, clave de 8 a 128 caracteres) y crea el
  usuario con rol ADMIN y cargo ADMINISTRADOR_SISTEMA.
- Si el correo ya existe, no cambia nada. Se puede correr varias veces.
- En desarrollo no hace falta: `datos_prueba` + `claves_prueba` ya crean `admin@reservas.test`.

## Pruebas

Archivos: `tests/conftest.py`, `tests/test_usuarios.py` (53 casos), `tests/test_registro.py` (21 casos).

- Usan una base aparte, `reservas_test`, en el mismo Postgres del compose. Se crea sola y cada
  prueba empieza con las tablas vacías. La base `reservas` de desarrollo no se toca.
- Si `TEST_DATABASE_URL` no termina en `reservas_test`, pytest se detiene antes de correr nada.
- Si los routers de usuarios o de registro no están registrados en `app/api/v1/router.py`,
  `conftest.py` los registra para poder probarlos.

Cómo correrlas:

```
docker compose exec api pip install -r requirements-dev.txt
docker compose exec api python -m pytest
```

**Importante:** el `pip install` dentro del contenedor **se pierde al reconstruir la imagen**
(`docker compose up --build`) o al recrear el contenedor. Para que quede fijo hay que agregarlo a
la imagen solo en desarrollo. Opción recomendada, con un argumento de construcción para que
producción no cargue pytest:

En el `Dockerfile`, después de `RUN pip install -r requirements.txt`:

```dockerfile
ARG INSTALAR_DEV=false
COPY requirements-dev.txt .
RUN if [ "$INSTALAR_DEV" = "true" ]; then pip install -r requirements-dev.txt; fi
```

Y en `compose.yaml`, en el servicio `api`, cambiar `build: .` por:

```yaml
    build:
      context: .
      args:
        INSTALAR_DEV: "true"
```

## Pendientes

1. **Reset de contraseña por parte del ADMIN.** No hay endpoint para que un ADMIN asigne una clave
   nueva a un usuario. Hoy `PATCH /usuarios/{id}` rechaza el campo `clave`. Propuesta:
   `PATCH /api/v1/usuarios/{id}/clave` (solo ADMIN) con la misma validación de 8–128 caracteres.
2. **Aprobador degradado que sigue en `espacio_aprobador`.** Si a un APROBADOR se le cambia el rol,
   sus filas en `espacio_aprobador` se conservan. No da permisos: revisar, aprobar y rechazar exigen
   rol APROBADOR. Pero si más adelante vuelve a ser APROBADOR, recupera automáticamente los mismos
   espacios. Falta decidir si al degradarlo se deben quitar esas asignaciones o si es el
   comportamiento deseado.
3. **Límite de intentos en el registro.** `POST /auth/registro` es público y no tiene rate
   limiting: un bot podría crear muchas cuentas con correos `@ecci.edu.co` inventados. Restringir
   el dominio reduce el riesgo, pero no lo elimina. Opciones: límite por IP (por ejemplo `slowapi`)
   o confirmar el correo con un enlace antes de activar la cuenta.
4. **Campos no incluidos:** `apellido`, `documento` y `fecha_actualizacion`. Agregarlos exige
   cambiar `app/models/modelos.py` y, como no hay Alembic, un `ALTER TABLE` manual sobre la tabla
   existente (`create_all` no altera tablas que ya existen).
