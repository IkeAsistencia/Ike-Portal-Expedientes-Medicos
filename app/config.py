"""
Configuración de la aplicación, leída de variables de entorno / archivo .env.

IMPORTANTE (seguridad de credenciales):
- Nunca pongas valores reales en este archivo ni en el código: siempre se
  leen de `.env` (ver `.env.example`), archivo que NO se debe subir a
  control de versiones (ver `.gitignore`) y que debe vivir en el ambiente
  restringido que tú definas.
- Se soportan dos modos de conexión a SQL Server (DB_AUTH_MODE):
    "windows" -> Autenticación integrada de Windows (Trusted_Connection=yes,
                 sin usuario/contraseña en ningún lado).
    "sql"     -> Autenticación de SQL Server (usuario/contraseña, que SÍ
                 debes llenar tú directamente en tu .env local — nunca los
                 compartas por chat ni los subas a un repositorio).
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Conexión a SQL Server ---
    db_auth_mode: str = "windows"  # "windows" | "sql"
    db_server: str
    db_name: str
    db_driver: str = "ODBC Driver 17 for SQL Server"

    # Solo se usan si db_auth_mode == "sql". Déjalos vacíos en modo Windows.
    db_user: Optional[str] = None
    db_password: Optional[str] = None

    # --- Base local (SQLite) para datos que NO viven en SQL Server ---
    # (estatus del expediente, grid de Configuración Cuentas)
    local_db_path: str = "./data/app_local.db"

    # --- Catálogo de cuentas con restricción fija por default (ver sql/README.md) ---
    # (el catálogo de subservicios ya NO usa una lista fija: ahora es
    # dinámico en cascada del combo Servicio, vía dbo.sp_GetSubServicios2)
    cuentas_permitidas: Optional[str] = "2819,2868,1366,2806,2654,1519"

    # --- Correo a proveedores (ver app/services/email_service.py) ---
    # Mientras no se configure un SMTP real, el envío queda "simulado"
    # (se registra en el log pero no se manda un correo de verdad).
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_remitente: Optional[str] = None
    smtp_usar_tls: bool = True

    # --- Sesión / JWT emitido por esta app tras el login ---
    # Genera uno propio por ambiente, ej: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret_key: str = "CAMBIA-ESTE-VALOR-EN-TU-.env"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 horas

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def connection_string(self) -> str:
        base = f"DRIVER={{{self.db_driver}}};SERVER={self.db_server};DATABASE={self.db_name};"
        # El ODBC Driver 18 exige TLS y valida el certificado del servidor
        # por default; en un SQL Server de desarrollo normalmente no hay uno
        # válido instalado, así que se confía en el certificado explícitamente.
        if "ODBC Driver 18" in self.db_driver:
            base += "Encrypt=yes;TrustServerCertificate=yes;"
        if self.db_auth_mode == "sql":
            return base + f"UID={self.db_user};PWD={self.db_password};"
        return base + "Trusted_Connection=yes;"

    def parse_int_list(self, csv_value: Optional[str]) -> list[int]:
        """Convierte 'a,b,c' en [a, b, c] para armar un TVP. Vacío/None -> []."""
        if not csv_value or not csv_value.strip():
            return []
        return [int(v.strip()) for v in csv_value.split(",") if v.strip()]

    @property
    def smtp_configurado(self) -> bool:
        return bool(self.smtp_host and self.smtp_remitente)


@lru_cache
def get_settings() -> "Settings":
    return Settings()
