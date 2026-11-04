import re
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.repositories.accesos_repo import (
    ENTIDADES_MEXICO,
    PERFIL_ADMINISTRADOR,
    PERFIL_PROVEEDOR,
    SIN_APLICA,
)

MENSAJE_REGLA_PASSWORD = (
    "La contraseña debe tener al menos 8 caracteres, con al menos una mayúscula, "
    "una minúscula, un número y un carácter especial (ej. !@#$%&*)."
)

# Cabina y Proveedor: RFC de 10 caracteres (4 letras + 6 números). Administrador:
# se le pide además el primer caracter de la homoclave (11 en total), porque hay
# más de una persona cuyo RFC de 10 caracteres coincide y así se distinguen.
PATRON_RFC = re.compile(r"^[A-Za-z]{4}\d{6}$")
PATRON_RFC_ADMINISTRADOR = re.compile(r"^[A-Za-z]{4}\d{6}[A-Za-z0-9]$")
MENSAJE_REGLA_RFC = "El RFC debe tener 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456)."
MENSAJE_REGLA_RFC_ADMINISTRADOR = (
    "El RFC del Administrador debe tener 11 caracteres: 4 letras, 6 números y el "
    "primer caracter de la homoclave (ej. ABCD123456Z)."
)
LARGO_MAXIMO_RFC = 11


def _cumple_regla_password(password: str) -> bool:
    return bool(
        len(password) >= 8
        and re.search(r"[a-z]", password)
        and re.search(r"[A-Z]", password)
        and re.search(r"\d", password)
        and re.search(r"[^A-Za-z0-9]", password)
    )


class RfcEstadoInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=LARGO_MAXIMO_RFC)


class RfcEstadoResponse(BaseModel):
    autorizado: bool
    tiene_password: bool
    nombre: Optional[str] = None


class CrearPasswordInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=LARGO_MAXIMO_RFC)
    # SecretStr para que la contraseña no pueda salir por un repr, un
    # model_dump ni el "input" de un error de validación (CWE-359) -- ver la
    # nota en app/schemas/auth.py.
    password: SecretStr = Field(..., min_length=8, max_length=40)

    @field_validator("password")
    @classmethod
    def _validar_password(cls, v: SecretStr) -> SecretStr:
        if not _cumple_regla_password(v.get_secret_value()):
            raise ValueError(MENSAJE_REGLA_PASSWORD)
        return v


class RfcLoginInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=LARGO_MAXIMO_RFC)
    password: SecretStr = Field(..., min_length=1, max_length=40)


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
    rfc: str = Field(..., min_length=1, max_length=LARGO_MAXIMO_RFC)
    nombre: str = Field(..., min_length=1, max_length=120)
    perfil: int = Field(..., ge=1, le=3)
    entidad: Optional[str] = None  # obligatoria solo si perfil == Proveedor
    correo: Optional[str] = None  # obligatorio solo si perfil == Proveedor

    @field_validator("rfc")
    @classmethod
    def _normalizar_rfc(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _validar_rfc_segun_perfil(self):
        # El Administrador lleva el primer caracter de la homoclave (11) porque
        # de otro modo el RFC de 10 caracteres no distingue entre dos personas.
        if self.perfil == PERFIL_ADMINISTRADOR:
            if not PATRON_RFC_ADMINISTRADOR.match(self.rfc):
                raise ValueError(MENSAJE_REGLA_RFC_ADMINISTRADOR)
        elif not PATRON_RFC.match(self.rfc):
            raise ValueError(MENSAJE_REGLA_RFC)
        return self

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
