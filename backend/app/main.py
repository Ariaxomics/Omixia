from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.db.indexes import ensure_indexes
from src.extensions import mongo_client, redis_client
from src.request_context import reset_current_request, set_current_request
from src.routers.api_v1 import router as api_v1_router
from src.routers.portal import router as portal_router
from src.routers.web import router as web_router
from src.session import load_session, set_session_cookie


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_client.init_app()
    redis_client.init_app()
    try:
        ensure_indexes()
    except Exception as e:
        print(f"Mongo not ready yet: {e}")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def session_and_context_middleware(request: Request, call_next):
    token = set_current_request(request)
    request.state.session = load_session(request)
    try:
        response = await call_next(request)
    finally:
        reset_current_request(token)
    set_session_cookie(response, request.state.session)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


app.include_router(api_v1_router)
app.include_router(web_router)
app.include_router(portal_router)
