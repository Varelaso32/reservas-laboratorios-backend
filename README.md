# Reservas Laboratorios - Backend

API REST para la gestión de reservas de laboratorios y salas, construida con **FastAPI** (Python 3.10+).

## Requisitos previos

- Python **3.10 o superior**
- `pip`

## Instalación

Crea y activa un entorno virtual, e instala las dependencias:

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

pip install -r requirements.txt
```

## Configuración

Copia el siguiente contenido en un archivo `.env` en la raíz del proyecto:

```env
PROJECT_NAME=Reservas Laboratorios API
PROJECT_VERSION=0.1.0
API_V1_STR=/api/v1
```

Todos los valores son opcionales; la aplicación usa estos valores por defecto si el archivo no existe.

## Ejecución

```bash
python -m uvicorn app.main:app --reload
```

El flag `--reload` reinicia el servidor automáticamente al guardar cambios.

## Documentación de la API

| Recurso | URL |
|---|---|
| API | `http://127.0.0.1:8000/` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI JSON | `http://127.0.0.1:8000/api/v1/openapi.json` |

## Pruebas

```bash
pytest tests/
```

## Estructura del proyecto

```
app/
├── api/v1/           # Endpoints HTTP de la API
├── core/             # Configuración de la aplicación
├── models/           # Modelos de base de datos (SQLAlchemy)
├── schemas/          # Esquemas Pydantic de entrada/salida
├── services/         # Lógica de negocio
├── utils/            # Utilidades transversales
└── main.py           # Punto de entrada de la aplicación
tests/                # Pruebas automatizadas
requirements.txt      # Dependencias del proyecto
```