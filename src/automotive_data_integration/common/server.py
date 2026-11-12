import os

import uvicorn
from fastapi import FastAPI


def serve(app: FastAPI) -> None:
    """Run one service with the host and port supplied by the environment."""
    uvicorn.run(
        app,
        host=os.environ.get("APP_HOST", "0.0.0.0"),
        port=int(os.environ.get("APP_PORT", "8000")),
    )
