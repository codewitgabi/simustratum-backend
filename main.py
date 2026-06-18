import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from sqlalchemy.exc import (
    DataError,
    IntegrityError,
    MultipleResultsFound,
    NoResultFound,
    OperationalError,
    ProgrammingError,
    SQLAlchemyError,
)

from api import database
from api.v1.middlewares.errors import (
    general_exception_handler,
    http_exception_handler,
    sqlalchemy_data_error_handler,
    sqlalchemy_generic_error_handler,
    sqlalchemy_integrity_error_handler,
    sqlalchemy_multiple_results_found_handler,
    sqlalchemy_no_result_found_handler,
    sqlalchemy_operational_error_handler,
    sqlalchemy_programming_error_handler,
    starlette_http_exception_handler,
    validation_exception_handler,
)
from api.v1.middlewares.logging import LoggingMiddleware
from api.v1.routes import v1_router
from api.v1.services import qdrant_client
from api.v1.utils.config import config
from api.v1.utils.logger import setup_logger

setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    await qdrant_client.connect()
    yield
    await qdrant_client.disconnect()
    await database.disconnect()


app = FastAPI(
    title="Simustratum API",
    lifespan=lifespan,
    version="1.0.0",
    swagger_ui_parameters={"defaultModelsExpandDepth": -1},
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        config.ALLOWED_ORIGINS.split(",") if config.ALLOWED_ORIGINS else ["*"]
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LoggingMiddleware)

# Exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(IntegrityError, sqlalchemy_integrity_error_handler)
app.add_exception_handler(OperationalError, sqlalchemy_operational_error_handler)
app.add_exception_handler(DataError, sqlalchemy_data_error_handler)
app.add_exception_handler(ProgrammingError, sqlalchemy_programming_error_handler)
app.add_exception_handler(NoResultFound, sqlalchemy_no_result_found_handler)
app.add_exception_handler(MultipleResultsFound, sqlalchemy_multiple_results_found_handler)
app.add_exception_handler(SQLAlchemyError, sqlalchemy_generic_error_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.include_router(v1_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.PORT)
