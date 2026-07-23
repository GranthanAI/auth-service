from fastapi import FastAPI
from app.api.routers import auth, users

app = FastAPI(
    title="Granthan Auth Service",
    description="Authentication and Identity Management Microservice for Granthan",
    version="1.0.0"
)

# Register Routers
app.include_router(auth.router)
app.include_router(users.router)

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Granthan Auth Service.",
        "documentation": "/docs"
    }
