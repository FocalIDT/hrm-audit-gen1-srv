from app.utils.validate_configs import validate_config_vars

validate_config_vars()

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import app.entity  # noqa: E402,F401
from app.config.mysql import Base, engine  # noqa: E402
from app.config.schema_setup import install_immutability_triggers  # noqa: E402
from app.controller import all_routers  # noqa: E402
from app.exception.exception_handler import add_exception_handler  # noqa: E402

app = FastAPI(description='HRM Audit Log API Service', version="1.0", title='HRM Audit Log API')

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_origins=["*"],
    expose_headers=["Content-Disposition"],
)

Base.metadata.create_all(bind=engine)
install_immutability_triggers(engine)

app.include_router(all_routers)
add_exception_handler(app)

if __name__ == '__main__':
    uvicorn.run(app, host="0.0.0.0", port=8016)
