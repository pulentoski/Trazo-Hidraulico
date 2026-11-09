"""Configuración de la API, leída desde variables de entorno (.env)."""
from functools import lru_cache

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
    max_ortho_mb: int = 500  # tamaño máximo de una ortofoto subida
    ortho_dir: str = "/data/ortho"  # almacenamiento compartido de ortofotos (volumen)

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
