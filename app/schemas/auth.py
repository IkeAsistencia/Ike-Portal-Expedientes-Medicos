from pydantic import BaseModel, Field, SecretStr


class LoginInput(BaseModel):
    """Body de POST /auth/login (pantalla de acceso al aplicativo)."""

    usuario: str = Field(..., min_length=1, max_length=15)
    # SecretStr: el valor queda encapsulado y su repr/model_dump muestran
    # "**********", así la contraseña no puede escaparse por accidente en un
    # log, una traza o una respuesta (CWE-359). Para usarla de verdad hay
    # que pedirla explícito con .get_secret_value().
    password: SecretStr = Field(..., min_length=1, max_length=20)
    # NOTA: el SP legado (@pContraseña varchar(10)) solo soporta 10
    # caracteres -- ver LARGO_MAXIMO_PASSWORD_SP en auth_repo.py, que
    # rechaza explícito cualquier contraseña más larga en vez de truncar.


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    cl_usr_app: int
    usuario: str
    nombre: str
