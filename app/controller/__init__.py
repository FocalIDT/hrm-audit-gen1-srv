from fastapi import APIRouter
from starlette.responses import HTMLResponse

from app.controller import audit_controller

all_routers = APIRouter()
all_routers.include_router(audit_controller.router)


@all_routers.get("/api/v1/ping")
async def ping():
    return {"status": "ok"}


# Root route
@all_routers.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content="""
        <html>
            <head><title>HRM Audit Log API Service</title></head>
            <body><h1>Welcome to HRM Audit Log API Service</h1></body>
        </html>
        """)
