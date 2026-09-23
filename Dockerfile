FROM python:3.13-slim

# PYTHONDONTWRITEBYTECODE evita que el contenedor cree carpetas __pycache__
# dentro de tu repo (la carpeta del proyecto está montada en /app).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Solo el código de la app: ni el .venv de Windows ni el .env entran a la imagen
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
