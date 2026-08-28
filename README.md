# Reservas Laboratorios - Backend

API backend para la gestión de reservas de laboratorios, construida con **FastAPI**.

---

## Estructura del proyecto

```
reservas-laboratorios-backend/
├── app/                           # Código principal de la aplicación
│   ├── __init__.py                # Marca la carpeta como paquete Python
│   ├── main.py                    # Creación de la app FastAPI y registro de routers
│   ├── api/                       # Capa de presentación (rutas HTTP / endpoints)
│   │   └── v1/                    # Versión 1 de la API
│   │       ├── router.py          # Agrupador que centraliza todos los routers de v1
│   │       └── endpoints/         # Endpoints por recurso
│   │           └── items.py       # CRUD de ejemplo (items)
│   ├── core/                      # Configuración central de la aplicación
│   │   ├── __init__.py
│   │   └── config.py              # Settings con pydantic-settings (lee variables del .env)
│   ├── models/                    # Modelos de base de datos (SQLAlchemy) - vacío por ahora
│   ├── schemas/                   # Esquemas Pydantic (validación de datos de entrada/salida)
│   │   └── item.py                # Schemas de ejemplo (Item, ItemCreate)
│   ├── services/                  # Lógica de negocio (capa de servicios) - vacío por ahora
│   └── utils/                     # Utilidades y helpers transversales - vacío por ahora
├── tests/                         # Tests automatizados - vacío por ahora
├── requirements.txt               # Dependencias del proyecto
├── .env                           # Variables de entorno (no se sube al repositorio)
└── .gitignore                     # Archivos ignorados por git
```

### ¿Para qué sirve cada carpeta?

| Carpeta          | Función                                                                 |
| ---------------- | ----------------------------------------------------------------------- |
| `app/main.py`    | Punto de entrada. Crea la instancia de `FastAPI`, carga la configuración e incluye los routers. |
| `app/api/`       | Expone la API al mundo: define las rutas HTTP y las respuestas.          |
| `app/api/v1/`    | Agrupa los endpoints de la versión 1 bajo `/api/v1`.                     |
| `app/api/v1/endpoints/` | Un archivo por recurso (ej. `items.py`). Cada router define sus propias rutas. |
| `app/core/`      | Configuración global (nombre del proyecto, versión, prefijo de API, credenciales, etc.). |
| `app/models/`    | **Modelos de base de datos** (Tablas cuando se integre SQLAlchemy/SQLite). |
| `app/schemas/`   | **Esquemas Pydantic**: validan los datos que entran y definen la forma de los datos que salen. |
| `app/services/`  | **Lógica de negocio**: reglas de la aplicación (ej. validar disponibilidad de un laboratorio). |
| `app/utils/`     | Funciones de uso general reutilizables (formateo, helpers, etc.).        |
| `tests/`         | Pruebas unitarias y de integración de la API.                            |

**Flujo de una petición:** `Cliente → app/api/v1/endpoints (ruta) → app/schemas (valida datos) → app/services (lógica) → app/models (persistencia)`.

> Las carpetas `models`, `services` y `utils` ya existen organizadas así para que solo agregues tu código cuando lo necesites.

---

## Versiones necesarias

| Paquete           | Requerido (requirements.txt) | Versión instalada |
| ----------------- | ----------------------------- | ----------------- |
| Python            | ≥ 3.10                        | 3.13.14           |
| fastapi           | ≥ 0.115.0                     | 0.136.0           |
| uvicorn[standard] | ≥ 0.30.0                      | 0.44.0            |
| pydantic          | ≥ 2.7.0                       | 2.13.2            |
| pydantic-settings | ≥ 2.3.0                       | 2.15.0            |

> `uvicorn` es el servidor ASGI que ejecuta la aplicación FastAPI.

---

## Cómo levantar el proyecto

### 1. Crear y activar entorno virtual (primera vez)

**Windows (cmd o PowerShell):**
```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno (opcional)

Crea un archivo `.env` en la raíz (modelo base):
```env
PROJECT_NAME=Reservas Laboratorios API
PROJECT_VERSION=0.1.0
API_V1_STR=/api/v1
```

### 4. Iniciar el servidor

```bash
python -m uvicorn app.main:app --reload
```

> Se usa `python -m uvicorn` (y no `uvicorn`) en caso de que el ejecutable no esté en el PATH. El flag `--reload` reinicia el servidor automáticamente al guardar cambios.

### 5. Acceder a la aplicación

| Recurso              | URL                          |
| -------------------- | ---------------------------- |
| API principal        | `http://127.0.0.1:8000/`     |
| Documentación Swagger| `http://127.0.0.1:8000/docs` |
| Documentación ReDoc  | `http://127.0.0.1:8000/redoc`|

Para detener el servidor presiona `Ctrl + C` en la terminal.

---

## Endpoints actuales (ejemplo de recurso "items")

| Método | Ruta             | Descripción                        |
| ------ | ---------------- | ---------------------------------- |
| GET    | `/`              | Mensaje de bienvenida              |
| GET    | `/api/v1/items/` | Lista todos los items              |
| GET    | `/api/v1/items/{id}` | Obtiene un item por su id      |
| POST   | `/api/v1/items/` | Crea un nuevo item (JSON)          |

Ejemplo de creación:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/items/" \
  -H "Content-Type: application/json" \
  -d '{"name": "Microscopio", "description": "Préstamo de laboratorio"}'
```

---

## Próximos pasos sugeridos

- Integrar **SQLAlchemy** o **SQLModel** para persistir los datos (modelos en `app/models/`).
- Crear los endpoints reales de **reservas**, **laboratorios** y **usuarios** en `app/api/v1/endpoints/`.
- Agregar **autenticación** (JWT) en `app/core/security.py` y dependencias en `app/api/deps.py`.
- Escribir tests en `tests/` (pytest + TestClient de FastAPI).