"""
Esquemas del portal nuevo (accesos por RFC): login, activación inicial,
alta y administración de accesos/perfiles (ver app/routers/acceso.py y
app/routers/admin_accesos.py). Valida el formato del RFC (10 caracteres,
4 letras + 6 números), la fuerza de la contraseña y, para el perfil
Proveedor, que traiga entidad y un correo con formato válido en el
dominio de la empresa.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from app.core.correo_empresa import MENSAJE_DOMINIO_NO_PERMITIDO, es_correo_de_empresa
from app.repositories.accesos_repo import (
    ENTIDADES_MEXICO,
    PERFIL_PROVEEDOR,
    SIN_APLICA,
)

MENSAJE_REGLA_PASSWORD = (
    "La contraseña debe tener al menos 8 caracteres, con al menos una mayúscula, "
    "una minúscula, un número y un carácter especial (ej. !@#$%&*)."
)

# RFC de acceso: 10 caracteres (4 letras + 6 números) para TODOS los perfiles.
# Una persona tiene un solo RFC aunque tenga varios perfiles (ver usuarios_perfiles).
PATRON_RFC = re.compile(r"^[A-Za-z]{4}\d{6}$")
MENSAJE_REGLA_RFC = "El RFC debe tener 10 caracteres: 4 letras seguidas de 6 números (ej. ABCD123456)."
LARGO_MAXIMO_RFC = 10


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


class ActivarPortalInput(CrearPasswordInput):
    """Body de POST /auth/activacion: crea al primer Administrador (ver accesos_repo.activar_portal)."""

    nombre: str = Field(..., min_length=1, max_length=120)

    @field_validator("rfc")
    @classmethod
    def _validar_rfc(cls, v: str) -> str:
        v = v.strip().upper()
        if not PATRON_RFC.match(v):
            raise ValueError(MENSAJE_REGLA_RFC)
        return v

    @field_validator("nombre")
    @classmethod
    def _validar_nombre(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Captura tu nombre.")
        return v


class ActivacionEstadoResponse(BaseModel):
    requerida: bool


class RfcLoginInput(BaseModel):
    rfc: str = Field(..., min_length=1, max_length=LARGO_MAXIMO_RFC)
    password: SecretStr = Field(..., min_length=1, max_length=40)
    # Solo cuando el RFC tiene más de un perfil: con cuál quiere entrar.
    perfil: Optional[int] = Field(default=None, ge=1, le=3)


class PerfilDisponible(BaseModel):
    perfil: int
    nombre: str


class PerfilesDisponiblesResponse(BaseModel):
    """
    Respuesta del login cuando el RFC tiene más de un perfil: todavía NO hay
    sesión; el login muestra "Entrar como" y repite la petición con `perfil`.
    """

    requiere_perfil: bool = True
    perfiles: list[PerfilDisponible]


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
            if not es_correo_de_empresa(self.correo):
                raise ValueError(MENSAJE_DOMINIO_NO_PERMITIDO)
            self.correo = self.correo.strip()
        else:
            # Cabina/Administrador no usan entidad ni correo -- "NA" en vez de vacío.
            self.entidad = SIN_APLICA
            self.correo = SIN_APLICA
        return self


class AgregarPerfilInput(BaseModel):
    """Body de POST /admin/accesos/{rfc}/perfiles: suma un perfil a una persona que ya tiene acceso."""

    perfil: int = Field(..., ge=1, le=3)
    entidad: Optional[str] = None  # obligatoria solo si perfil == Proveedor
    correo: Optional[str] = None  # obligatorio solo si perfil == Proveedor

    @model_validator(mode="after")
    def _validar_proveedor(self):
        if self.perfil == PERFIL_PROVEEDOR:
            if not self.entidad or self.entidad not in ENTIDADES_MEXICO:
                raise ValueError("Debes asignarle una entidad válida al perfil Proveedor.")
            if not self.correo or not _correo_valido(self.correo.strip()):
                raise ValueError("Debes asignarle un correo válido al perfil Proveedor.")
            if not es_correo_de_empresa(self.correo):
                raise ValueError(MENSAJE_DOMINIO_NO_PERMITIDO)
            self.correo = self.correo.strip()
        else:
            self.entidad = None
            self.correo = None
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


class CargaUsuariosFila(BaseModel):
    """Una fila del Excel de la carga masiva, con lo que se hizo (o se haría) con ella."""

    hoja: str
    renglon: int
    rfc: str
    nombre: str
    rol: str
    entidad: Optional[str] = None
    correo: Optional[str] = None
    # 'nuevo' | 'perfil_agregado' | 'ya_existia' | 'rechazada'
    resultado: str
    motivo: Optional[str] = None


class CargaUsuariosResponse(BaseModel):
    """Respuesta de POST /admin/accesos/carga-excel. Con aplicado=False es solo la vista previa."""

    aplicado: bool
    total: int
    nuevos: int
    perfiles_agregados: int
    ya_existian: int
    rechazadas: int
    filas: list[CargaUsuariosFila]


class AccesoListado(BaseModel):
    rfc: str
    nombre: str
    perfil: int  # el principal; todos los que tiene van en `perfiles`
    perfiles: list[int] = []
    tiene_password: bool
    fecha_alta: str
    activo: bool
    entidad: Optional[str] = None
    correo: Optional[str] = None
