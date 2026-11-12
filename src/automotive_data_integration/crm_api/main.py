from fastapi import FastAPI

from automotive_data_integration.common.health import health_router
from automotive_data_integration.common.server import serve
from automotive_data_integration.crm_api.routes import router as crm_router

app = FastAPI(title="crm-api")
app.include_router(health_router("crm-api"))
app.include_router(crm_router)


def main() -> None:
    serve(app)
