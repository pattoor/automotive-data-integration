from fastapi import APIRouter


def health_router(service_name: str) -> APIRouter:
    """Return a router exposing the liveness contract of one service."""
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": service_name}

    return router
