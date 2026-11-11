"""Configuración de la API, leída desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    postgres_db: str = "trazo"
    postgres_user: str = "trazo"
    postgres_password: str = ""
    db_host: str = "db"
    db_port: int = 5432

    redis_host: str = "cache"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    length_srid: int = 32719
    default_map_center_lat: float = -33.4489
    default_map_center_lng: float = -70.6693

    epanet_build_info: str = "/opt/epanet/BUILD_INFO"
    runepanet: str = "/usr/local/bin/runepanet"
    report_dir: str | None = None

    # Protección mínima para publicar (sin usuarios todavía)
    rate_limit_per_minute: int = 300  # solicitudes a /api por IP y minuto; 0 desactiva
    max_inp_mb: int = 20  # tamaño máximo del .inp importado (Caddy aplica el mismo límite)
    max_xlsx_mb: int = 20  # tamaño máximo de planillas Excel/CSV importadas
    # Tamaño máximo de una ortofoto (total de la subida por partes). ORTHO_MAX_MB; MAX_ORTHO_MB se acepta por
    # compatibilidad con instalaciones anteriores.
    max_ortho_mb: int = Field(2048, validation_alias=AliasChoices("ORTHO_MAX_MB", "MAX_ORTHO_MB", "max_ortho_mb"))
    ortho_part_mb: int = 16  # ORTHO_PART_MB: tamaño de cada parte (debe ser menor que ORTHO_CHUNK_MB, el límite por parte de Caddy)
    ortho_disk_factor: float = 3.0  # espacio libre exigido: tamaño × factor (original, intermedios y COG)
    ortho_gdal_cachemax_mb: int = 256  # caché de bloques de GDAL en el worker (memoria acotada)
    ortho_warp_mem_mb: int = 256  # memoria de trabajo de gdalwarp
    ortho_dir: str = "/data/ortho"  # almacenamiento compartido de ortofotos (volumen)

    # Clave para cifrar configuración sensible en la base (key de Google Maps): Fernet, 32 bytes en base64 url-safe.
    # Generar con: python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
    settings_secret_key: str = ""

    # Autenticación y sesiones (etapa 5)
    session_hours: float = 12.0  # expiración de la sesión
    cookie_secure: bool = True  # cookie solo por HTTPS (en http://localhost los navegadores la aceptan igual)
    cookie_name: str = "trazo_session"
    login_max_attempts: int = 5  # intentos fallidos antes del bloqueo temporal
    login_lockout_minutes: int = 15
    login_rate_per_minute: int = 10  # intentos de ingreso por IP y minuto
    mfa_required_for_admins: bool = True  # administradores (de organización y de plataforma) deben usar TOTP
    password_min_length: int = 10
    public_url: str = "http://localhost:8080"  # para enlaces de recuperación e invitación
    reset_token_hours: int = 24
    invite_token_days: int = 7
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_tls: bool = True

    # Umbrales del validador (advertencias)
    short_pipe_m: float = 1.0
    elevation_jump_m: float = 50.0

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.db_host}:{self.db_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
