"""
Base class for managers that require a PostgreSQL client.
"""

from ..postgresql_client import PostgreSQLClient


class BaseManager:
    """
    Provides a shared __init__ pattern for manager classes that accept an
    optional PostgreSQLClient and create one if none is supplied.
    """

    def __init__(self, pg_client=None):
        """
        @param pg_client: PostgreSQLClient instance. If None, a new one is created.
        """
        self.pg_client = pg_client if pg_client is not None else PostgreSQLClient()
