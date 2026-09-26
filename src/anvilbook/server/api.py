import logging
import os

from fastapi import FastAPI

from .db import Database

log = logging.getLogger(__name__)


def create_server(database: Database | None = None) -> FastAPI:
    db: Database = database or Database()
    app = FastAPI(title='anvilbook server')

    @app.get('/healthz')
    def healthz():
        db.query('SELECT 1')
        return {'ok': True}

    return app


def run() -> None:
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    uvicorn.run(create_server(), host='0.0.0.0', port=int(os.environ.get('PORT', 8000)))
