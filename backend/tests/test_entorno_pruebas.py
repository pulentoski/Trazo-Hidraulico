"""Las pruebas usan exclusivamente la base de datos y la caché de prueba."""
from sqlalchemy import text

from app.core.cache import get_redis
from app.core.config import get_settings
from app.core.db import get_engine


def test_configuracion_apunta_a_la_base_de_prueba():
    s = get_settings()
    assert s.postgres_db.endswith("_test")
    assert s.database_url.rsplit("/", 1)[1] == s.postgres_db
    assert s.redis_db != 0


def test_conexiones_reales_son_las_de_prueba(client):
    with get_engine().connect() as conn:
        assert conn.execute(text("SELECT current_database()")).scalar().endswith("_test")
    assert get_redis().connection_pool.connection_kwargs["db"] != 0
