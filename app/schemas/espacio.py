from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TipoEspacio


class EspacioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(description="Identificador del espacio", examples=[1])
    nombre: str = Field(description="Nombre del laboratorio o sala", examples=["Laboratorio de Redes"])
    tipo: TipoEspacio = Field(description="LABORATORIO o SALA")
    capacidad: int = Field(description="Número máximo de personas", examples=[25])
    ubicacion: str | None = Field(description="Bloque y piso", examples=["Bloque A, piso 2"])
