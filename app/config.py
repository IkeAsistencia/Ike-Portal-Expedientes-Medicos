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

# Valor que trae jwt_secret_key si nadie lo configuró -- ver validar() más
# abajo, que impide arrancar la app con este valor puesto (ya está en el
# código fuente, cualquiera que lo lea podría firmar tokens válidos).
JWT_SECRET_KEY_DEFAULT = "CAMBIA-ESTE-VALOR-EN-TU-.env"


class Settings(BaseSettings):
    # --- Conexión a SQL Server ---
    db_auth_mode: str = "windows"  # "windows" | "sql"
    db_server: str
    db_name: str
    db_driver: str = "ODBC Driver 17 for SQL Server"

    # Solo se usan si db_auth_mode == "sql". Déjalos vacíos en modo Windows.
    db_user: Optional[str] = None
    db_password: Optional[str] = None

    # Solo aplica con ODBC Driver 18 (ver connection_string). En desarrollo el
    # SQL Server normalmente no tiene un certificado válido instalado, así que
    # se confía en él por default (True). ANTES de producción, pon un
    # certificado válido en el SQL Server y DB_TRUST_SERVER_CERTIFICATE=false
    # en ese .env -- si no, la conexión queda sin validar la identidad del
    # servidor (expuesta a MITM en el enlace de red que uses).
    db_trust_server_certificate: bool = True

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
    # Mientras no se confirme de dónde sale el correo real de cada proveedor
    # (ver email_service.py), todo se manda aquí en vez de al proveedor real
    # -- útil para probar en un ambiente de desarrollo sin mandarle correos
    # a nadie más. Vacío = se manda a smtp_remitente, como antes.
    smtp_destinatario_prueba: Optional[str] = None

    # --- OpenRouter (ver app/services/openrouter_service.py) ---
    # Puerta de entrada a modelos de IA (OpenRouter normaliza el API de
    # varios proveedores). Cada llamada queda registrada en la base local
    # (tabla openrouter_iteraciones) con sus tokens y costo reales -- el
    # costo lo regresa OpenRouter mismo en cada respuesta (usage.cost), no
    # se calcula ni se estima aquí. Sin OPENROUTER_API_KEY, el endpoint
    # /openrouter rechaza la petición en vez de fallar a medias.
    openrouter_api_key: Optional[str] = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_modelo_default: str = "openai/gpt-4o-mini"
    # Recomendados por OpenRouter para identificar la app en su ranking
    # (openrouter.ai/docs: headers HTTP-Referer / X-Title) -- opcionales.
    openrouter_site_url: Optional[str] = None
    openrouter_app_name: str = "Portal Expedientes Médicos"

    # --- Sesión / JWT emitido por esta app tras el login ---
    # Genera uno propio por ambiente, ej: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret_key: str = JWT_SECRET_KEY_DEFAULT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 horas

    # --- Proxy delante de la app (ver app/core/red.py) ---
    # Cuántos proxies de confianza agregan su IP a X-Forwarded-For antes de
    # llegar a la app. La IP real del usuario es la que quedó en esa posición
    # contando desde el final (lo de antes lo pudo escribir el propio usuario):
    #   1 = un solo proxy (ALB solo, o nginx que reemplaza el encabezado)
    #   2 = CloudFront + ALB
    #   0 = sin proxy (se ignora X-Forwarded-For y se usa la IP de la conexión)
    proxies_confiables: int = 1

    # --- Login legado por usuario/contraseña de SISE (/auth/login y la
    # mutación login de GraphQL) ---
    # El portal entra solo por RFC; este login ya no se usa y queda apagado
    # para no dejar una puerta extra en producción. Solo se enciende para las
    # pruebas automatizadas o si algún cliente externo lo vuelve a necesitar.
    login_legado_habilitado: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def connection_string(self) -> str:
        base = f"DRIVER={{{self.db_driver}}};SERVER={self.db_server};DATABASE={self.db_name};"
        if "ODBC Driver 18" in self.db_driver:
            trust = "yes" if self.db_trust_server_certificate else "no"
            base += f"Encrypt=yes;TrustServerCertificate={trust};"
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

    @property
    def openrouter_configurado(self) -> bool:
        return bool(self.openrouter_api_key)


@lru_cache
def get_settings() -> "Settings":
    return Settings()


def validar_jwt_secret(settings: "Settings") -> None:
    """
    Llamar al arrancar la app (ver app/main.py: lifespan), NO desde
    get_settings() -- si no, construir Settings() en cualquier lado (incluso
    solo para importar un módulo, como en las pruebas) tronaría por no tener
    todavía un JWT_SECRET_KEY real configurado.
    """
    if settings.jwt_secret_key == JWT_SECRET_KEY_DEFAULT:
        raise RuntimeError(
            "JWT_SECRET_KEY sigue en su valor por default (inseguro: ya está en el "
            "código fuente). Genera uno real y ponlo en tu .env:\n"
            '    python -c "import secrets; print(secrets.token_hex(32))"'
        )


class ArranqueSettings(BaseSettings):
    """
    Configuración que SÍ hace falta al importar app.main (antes de que la
    app arranque de verdad): CORS y el toggle de GraphQL IDE. Separada de
    Settings a propósito -- Settings exige DB_SERVER/DB_NAME (sin default),
    así que construirla al importar el módulo (en vez de perezosamente, por
    request) rompería cualquier cosa que solo necesite importar app.main
    sin tener todavía un .env completo (ej. pytest recolectando las pruebas).
    """

    # El portal (frontend/) lo sirve esta misma app, así que no necesita CORS.
    # Por default no se permite ningún origen externo (lo seguro para
    # producción). Solo si un cliente externo consume la API desde otro
    # dominio, pon aquí sus URLs exactas separadas por coma; "*" permite
    # cualquier origen y solo debe usarse en desarrollo.
    cors_allowed_origins: str = ""

    # GraphiQL (explorador visual) e introspección: cómodos en desarrollo, pero
    # exponen el schema completo (todas las queries/mutations/tipos) sin
    # autenticación. Apagado por default; enciéndelo solo en desarrollo
    # (GRAPHQL_IDE_HABILITADO=true en tu .env local).
    graphql_ide_habilitado: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        """["*"] tal cual, o la lista de orígenes separados por coma sin espacios."""
        if self.cors_allowed_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_arranque_settings() -> "ArranqueSettings":
    return ArranqueSettings()
