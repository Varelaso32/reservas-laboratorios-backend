"""Crea el primer ADMIN del sistema a partir de variables de entorno.

Sirve para el arranque: POST /api/v1/usuarios exige ser ADMIN, así que el primero
se crea con este script. Si el correo ya existe no cambia nada. Se puede correr
varias veces.

Las variables se pasan en el comando, no en el .env (config.py rechaza variables
que no tiene declaradas):

    docker compose exec -e ADMIN_EMAIL=admin@ecci.edu.co -e ADMIN_NOMBRE="Administrador" \
        -e ADMIN_CLAVE='UnaClaveSegura2026*' api python -m app.utils.crear_admin
"""
import os
import sys

from pydantic import ValidationError

from app.core.database import SessionLocal
from app.models.enums import Cargo, Rol
from app.schemas.usuario import UsuarioCrear
from app.services import usuarios


def crear_admin() -> int:
    faltan = [v for v in ("ADMIN_EMAIL", "ADMIN_NOMBRE", "ADMIN_CLAVE") if not os.getenv(v)]
    if faltan:
        print(f"Faltan variables de entorno: {', '.join(faltan)}")
        return 1

    try:
        datos = UsuarioCrear(
            nombre=os.environ["ADMIN_NOMBRE"],
            email=os.environ["ADMIN_EMAIL"],
            clave=os.environ["ADMIN_CLAVE"],
            rol=Rol.ADMIN,
            cargo=Cargo.ADMINISTRADOR_SISTEMA,
        )
    except ValidationError as error:
        # Se muestran solo los mensajes: el input traería la clave en texto plano
        for e in error.errors():
            print(f"{e['loc'][0]}: {e['msg']}")
        return 1

    with SessionLocal() as db:
        try:
            admin = usuarios.crear(db, datos)
        except usuarios.ErrorUsuario as error:
            if error.codigo == 409:
                print(f"Ya existe un usuario con el correo {datos.email}. No se cambió nada.")
                return 0
            print(error.mensaje)
            return 1
    print(f"ADMIN creado: id={admin.id}, correo={admin.email}")
    return 0


if __name__ == "__main__":
    sys.exit(crear_admin())
