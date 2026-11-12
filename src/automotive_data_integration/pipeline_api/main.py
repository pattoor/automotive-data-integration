from fastapi import FastAPI

from automotive_data_integration.common.health import health_router
from automotive_data_integration.common.server import serve

app = FastAPI(title="pipeline-api")
app.include_router(health_router("pipeline-api"))


def main() -> None:
    serve(app)
