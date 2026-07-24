from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import auth, users, sessions, health
from app.api.middleware import SecurityHeadersMiddleware
from app.lifespan import lifespan
from app.core.config import settings

app = FastAPI(
    title="Granthan Auth Service",
    description="Authentication and Identity Management Microservice for Granthan",
    version="1.0.0",
    lifespan=lifespan
)

# Register Middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sessions.router)
app.include_router(health.router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Granthan Auth Service.",
        "documentation": "/docs"
    }
