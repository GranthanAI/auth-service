# Redis Integration Guide

This document describes how **Redis** is used within the Granthan Auth Service to enforce API rate limits, brute-force lockouts, and JWT access token blacklisting.

---

## 1. Connection Pool Registry

Located in: [app/cache/redis.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/cache/redis.py)

Redis operations are managed asynchronously using `redis.asyncio`. 
* **Connection Pool:** We initialize a single connection pool (`ConnectionPool.from_url`) during server startup inside the FastAPI lifespan hook.
* **Resilience (Sandbox Fallback):** If the Redis server is offline during startup, the initialization logs the warning and flags connection status, allowing the service to run with local **in-memory fallbacks** (ideal for local testing).

---

## 2. Core Redis Implementations

We use Redis for three primary caching and security features:

### 2.1 Brute-Force Login Lockout (`LoginAttemptCache`)
Located in: [app/cache/login_attempt_cache.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/cache/login_attempt_cache.py)

To prevent dictionary attacks against user passwords, the login endpoint tracks failed login attempts.
* **Mechanism:**
  1. If a login fails, we increment a counter key `failed_attempts:{email}`.
  2. The key is set to expire after `LOCKOUT_DURATION_SECONDS` (30 minutes by default).
  3. If the counter reaches `FAILED_LOGIN_LIMIT` (5 attempts), the server rejects login requests for that email with a `403 Forbidden` error.
  4. On successful login, the counter key is deleted.

### 2.2 IP-Based Rate Limiting (`RedisRateLimiter`)
Located in: [app/security/rate_limiter.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/security/rate_limiter.py)

Protects endpoint gateways (like registration and login) from spam and DDoS spikes.
* **Mechanism:**
  1. We store request counts per IP on keys: `rate:{client_ip}:{endpoint_name}`.
  2. The key automatically expires after the window limit (60 seconds).
  3. If the request count exceeds the limit (e.g., 5 requests per minute for register/login), the middleware rejects the request immediately with an `HTTP 429 Too Many Requests` status code.

### 2.3 JWT Access Token Blacklisting (`JWTBlacklist`)
Located in: [app/cache/jwt_blacklist.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/cache/jwt_blacklist.py)

While JSON Web Tokens (JWTs) are designed to be stateless, we need a way to revoke them immediately in case of a **Logout** or **Password Change/Reset** before they naturally expire.
* **Mechanism:**
  1. When a user logs out or changes their password, we extract the unique token ID (`jti` claim) and its expiration timestamp (`exp`).
  2. We insert the key `blacklist:{jti}` into Redis.
  3. The key TTL (Time-To-Live) is set to the token's remaining time-to-live (`exp - current_time`). Once it passes the expiry, Redis garbage-collects the key.
  4. Our HTTP Bearer authentication dependency check ([deps.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/api/deps.py)) does an async lookup:
     ```python
     if await JWTBlacklist.is_blacklisted(payload["jti"], redis=redis):
         raise HTTPException(status_code=401, detail="Token has been revoked.")
     ```

---

## 3. High-Resilience Fallback Strategy

Because memory databases can occasionally restart or disconnect under massive network stress, our cache classes implement a **resilient fail-safe structure**:

```python
    @classmethod
    async def is_blacklisted(cls, jti: str, redis: Redis | None = None) -> bool:
        key = f"blacklist:{jti}"
        if redis:
            try:
                # Primary: Query high-speed Redis database
                exists = await redis.exists(key)
                return exists > 0
            except Exception as e:
                logger.error(f"Redis error: {e}")

        # Secondary Fail-safe: Fallback to thread-safe local python dictionary
        now = time.time()
        expire_time = cls._fallback_blacklist.get(jti)
        if expire_time:
            if now > expire_time:
                cls._fallback_blacklist.pop(jti, None)
                return False
            return True
        return False
```
* **Why it matters:** If the Redis container crashes or drops connection sockets, the Auth Service continues running smoothly without raising HTTP 500 errors, utilizing local memory structures to preserve rate limits and locks.
