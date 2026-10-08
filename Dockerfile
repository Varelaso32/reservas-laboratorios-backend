FROM python:3.13-slim

# PYTHONDONTWRITEBYTECODE evita que el contenedor cree carpetas __pycache__
# dentro de tu repo (la carpeta del proyecto está montada en /app).
# PIP_CERT, REQUESTS_CA_BUNDLE y SSL_CERT_FILE hacen que pip y la app usen el
# almacén de certificados del sistema.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Certificados raíz extra para proxies corporativos (inspección SSL).
# Si la carpeta certs/ solo tiene el .gitkeep no pasa nada.
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Solo el código de la app: ni el .venv de Windows ni el .env entran a la imagen
COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
