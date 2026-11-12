from fastapi import FastAPI

from automotive_data_integration.common.health import health_router
from automotive_data_integration.common.server import serve

app = FastAPI(title="crm-api")
app.include_router(health_router("crm-api"))


def main() -> None:
    serve(app)
