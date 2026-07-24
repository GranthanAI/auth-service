import uuid
import logging
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger("app.api.middleware")

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Correlation/Trace ID Integration
        trace_id = request.headers.get("X-Request-ID")
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        # Save trace_id in request state context
        request.state.trace_id = trace_id
        
        # 2. Strict Origin/CSRF Verification on sensitive token/session endpoints
        if request.url.path in ["/auth/refresh", "/auth/logout"]:
            origin = request.headers.get("origin")
            if origin:
                if origin not in settings.ALLOWED_CORS_ORIGINS:
                    logger.warning(f"CSRF CORS validation failed for origin '{origin}' on route '{request.url.path}'")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF Check Failed: Unauthorized Origin."}
                    )

        # Execute endpoint execution
        response: Response = await call_next(request)
        
        # 3. Secure Response Headers (HSTS, Frame Protection, Clickjacking)
        response.headers["X-Request-ID"] = trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response
