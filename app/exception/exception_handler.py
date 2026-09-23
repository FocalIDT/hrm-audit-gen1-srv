from fastapi import Request
from fastapi.responses import JSONResponse

from app.config.logging_config import get_logger
from app.exception import BaseAppException
from app.model.generic_response import GenericResponse

logger = get_logger(__name__)


def add_exception_handler(app):
    @app.exception_handler(BaseAppException)
    async def base_exception_handler(request: Request, exc: BaseAppException):
        logger.warning(f"{request.method} {request.url.path} -> {exc.status}: {exc.message}")
        return JSONResponse(status_code=exc.status,
                            content=GenericResponse.failed(message=exc.message, results=None,
                                                           status_code=exc.status).to_dict())

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(status_code=500,
                            content=GenericResponse.failed(message="Internal server error", results=None,
                                                           status_code=500).to_dict())
