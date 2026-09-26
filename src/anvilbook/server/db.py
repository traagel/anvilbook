import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

SCHEMA = (Path(__file__).parent / 'schema.sql').read_text()
TABLES = ['character_recipes', 'character_skills', 'characters', 'prices', 'scans', 'tokens',
          'users', 'realms']


class Database:
    def __init__(self, url: str | None = None):
        self.url = url or os.environ['DATABASE_URL']
        with self.connect() as conn:
            conn.execute(SCHEMA)

    @contextmanager
    def connect(self):
        with psycopg.connect(self.url, row_factory=dict_row, autocommit=True) as conn:
            yield conn

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.connect() as conn:
            return conn.execute(sql, args).fetchall()

    def execute(self, sql: str, args: tuple = ()) -> dict | None:
        with self.connect() as conn:
            cursor = conn.execute(sql, args)
            return cursor.fetchone() if cursor.description else None

    def reset(self) -> None:
        """Empties every table. Tests only."""
        with self.connect() as conn:
            conn.execute('TRUNCATE ' + ', '.join(TABLES) + ' RESTART IDENTITY CASCADE')
