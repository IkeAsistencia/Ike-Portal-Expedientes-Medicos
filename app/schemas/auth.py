from pydantic import BaseModel, Field


class LoginInput(BaseModel):
    """Body de POST /auth/login (pantalla de acceso al aplicativo)."""

    usuario: str = Field(..., min_length=1, max_length=15)
    password: str = Field(..., min_length=1, max_length=20)
    # NOTA: el SP legado (@pContraseña varchar(10)) solo soporta 10
    # caracteres; ver sql/05_login_sp_EncriptDesEncriptPassword_NOTAS.md.


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cl_usr_app: int
    usuario: str
    nombre: str
