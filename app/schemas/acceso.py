import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.repositories.accesos_repo import ENTIDADES_MEXICO, PERFIL_PROVEEDOR, SIN_APLICA

MENSAJE_REGLA_PASSWORD = (
    "La contraseña debe tener al menos 8 caracteres, con al menos una mayúscula, "
    "una minúscula, un número y un carácter especial (ej. !@#$%&*)."
)

PATRON_RFC = re.compile(r"^[A-Za-z]{4}\d{6}$")
MENSAJE_REGLA_RFC = "El RFC debe tener 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456)."


def _cumple_regla_password(password: str) -> bool:
    return bool(
        len(password) >= 8
        and re.search(r"[a-z]", password)
        and re.search(r"[A-Z]", password)
        and re.search(r"\d", password)
        and re.search(r"[^A-Za-z0-9]", password)
    )


class RfcEstadoInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=20)


class RfcEstadoResponse(BaseModel):
    autorizado: bool
    tiene_password: bool
    nombre: Optional[str] = None


class CrearPasswordInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=8, max_length=40)

    @field_validator("password")
    @classmethod
    def _validar_password(cls, v: str) -> str:
        if not _cumple_regla_password(v):
            raise ValueError(MENSAJE_REGLA_PASSWORD)
        return v


class RfcLoginInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=20)
    password: str = Field(..., min_length=1, max_length=40)


class AccesoLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rfc: str
    nombre: str
    perfil: int


def _correo_valido(correo: str) -> bool:
    # Validación simple de formato -- no se manda correo real de confirmación,
    # solo evita errores de dedo obvios (falta @, falta dominio, etc.).
    partes = correo.split("@")
    return len(partes) == 2 and bool(partes[0]) and "." in partes[1] and not partes[1].startswith(".")


class AltaAccesoInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=120)
    perfil: int = Field(..., ge=1, le=3)
    entidad: Optional[str] = None  # obligatoria solo si perfil == Proveedor
    correo: Optional[str] = None  # obligatorio solo si perfil == Proveedor

    @field_validator("rfc")
    @classmethod
    def _validar_rfc(cls, v: str) -> str:
        v = v.strip().upper()
        if not PATRON_RFC.match(v):
            raise ValueError(MENSAJE_REGLA_RFC)
        return v

    @model_validator(mode="after")
    def _validar_entidad_y_correo(self):
        if self.perfil == PERFIL_PROVEEDOR:
            if not self.entidad or not self.entidad.strip():
                raise ValueError("Debes asignarle una entidad al perfil Proveedor.")
            if self.entidad not in ENTIDADES_MEXICO:
                raise ValueError(f"Entidad inválida. Opciones: {', '.join(ENTIDADES_MEXICO)}")
            if not self.correo or not self.correo.strip():
                raise ValueError("Debes asignarle un correo al perfil Proveedor.")
            if not _correo_valido(self.correo.strip()):
                raise ValueError("El correo no tiene un formato válido.")
            self.correo = self.correo.strip()
        else:
            # Cabina/Administrador no usan entidad ni correo -- "NA" en vez de vacío.
            self.entidad = SIN_APLICA
            self.correo = SIN_APLICA
        return self


class ActualizarEntidadInput(BaseModel):
    """Body de POST /admin/accesos/{rfc}/entidad -- cambiar la entidad de un Proveedor ya creado."""

    entidad: str = Field(..., min_length=1)

    @field_validator("entidad")
    @classmethod
    def _validar_entidad(cls, v: str) -> str:
        if v not in ENTIDADES_MEXICO:
            raise ValueError(f"Entidad inválida. Opciones: {', '.join(ENTIDADES_MEXICO)}")
        return v


class AccesoListado(BaseModel):
    rfc: str
    nombre: str
    perfil: int
    tiene_password: bool
    fecha_alta: str
    activo: bool
    entidad: Optional[str] = None
    correo: Optional[str] = None
