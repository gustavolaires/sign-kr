from django.apps import AppConfig
from django.db.backends.signals import connection_created


def _register_sqlite_functions(connection, **kwargs):
    """Registra ``unaccent_lower`` em cada conexão SQLite (ver ``sign.search``)."""
    if connection.vendor != "sqlite":
        return
    from .search import unaccent_lower

    connection.connection.create_function(
        "unaccent_lower", 1, unaccent_lower, deterministic=True
    )


class SignConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'sign'

    def ready(self):
        connection_created.connect(_register_sqlite_functions)
