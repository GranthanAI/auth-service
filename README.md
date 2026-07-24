# Granthan Auth Service

An asynchronous, production-grade authentication, session, and identity management microservice built with **FastAPI**, **PostgreSQL**, **Redis**, and **Kafka**.

---

## 🚀 Key Features

* **Identity Management:** User onboarding, case-insensitive email constraints, profile updates, and email verification workflows.
* **Cryptographic Security:** Password hashing using the **Argon2id** algorithm and regex-enforced complexity rules.
* **Stateless access tokens (JWT):** short-lived signed JWTs.
* **Secure Cookie Session Management:** Token-Rotation-Rotation (RTR) using secure, `HttpOnly`, `SameSite=Strict`, `Secure` refresh token cookies.
* **Token Reuse & Compromise Detection:** If a revoked refresh token is reused, all active sibling sessions are instantly terminated.
* **Active Session Management:** APIs to list logged-in devices and revoke specific or all other devices (mass logouts).
* **Transactional Outbox Event Publisher:** Decouples database writes and message publishing to Kafka (using `select FOR UPDATE SKIP LOCKED` background polling threads) to guarantee **At-Least-Once Delivery** downstream.
* **Redis Caching & Lockouts:** Sliding counter brute-force lockout (5 failed logins lock for 30 mins), endpoint rate limiting, and JWT access token blacklists.
* **Security Middlewares:** correlation ID logging (`X-Request-ID`), frame options protection, and strict `Origin` header CSRF validation on refresh requests.
* **System Diagnostics:** `/health` endpoint checks database, Redis pool, and Kafka connectivity status.

---

## 🛠️ Technology Stack

* **Core Framework:** Python 3.12, FastAPI
* **Database:** PostgreSQL (with SQLAlchemy 2.0 Async ORM and `asyncpg` driver)
* **Caching & Lockout:** Redis (using `redis-py` async pool)
* **Message Broker:** Apache Kafka (using `aiokafka` client)
* **Dependency Manager:** `uv` (Fast environment sync and locking)

---

## 📂 Project Structure

```text
auth-service/
├── app/
│   ├── api/
│   │   ├── middleware.py      # Trace IDs, Security Headers, CSRF checks
│   │   ├── deps.py            # FastAPI DI (get_db, get_redis, get_current_user)
│   │   ├── routers/
│   │   │   ├── auth.py        # Login, Register, Recover, Verification
│   │   │   ├── users.py       # Profile and password changes
│   │   │   ├── sessions.py    # Active session management
│   │   │   └── health.py      # Dependency check probes
│   │   └── schemas/           # Pydantic validation schemas
│   ├── cache/                 # Redis managers, lockouts, blacklists
│   ├── core/                  # Settings configurations and exceptions
│   ├── db/                    # SQLAlchemy engine and session makers
│   ├── events/                # Kafka client connections and serializers
│   ├── models/                # SQLAlchemy database entities
│   ├── repositories/          # Database query wrappers
│   ├── security/              # Hashing, validator strength checks, rate limiters
│   ├── services/              # Domain orchestration services
│   ├── utils/                 # Device and user agent parsers
│   ├── workers/               # Background Outbox Poller Worker
│   └── lifespan.py            # Startup/Shutdown container hooks
├── docs/                      # Architectural specs and testing guides
├── docker-compose.yml         # Local stack setup (Redis, Zookeeper, Kafka)
├── init_db.py                 # PostgreSQL database setup script
├── Makefile                   # Developer shortcuts CLI
├── pyproject.toml             # Package dependencies manifest
└── README.md                  # This file
```

---

## ⚙️ Quick Start Setup

### Prerequisites
* Python 3.12+ (managed via `uv` recommended)
* Docker Desktop (for Redis and Kafka containers)
* Local PostgreSQL database running on port `5432` (password config in `.env`)

### 1. Sync Virtual Environment
Install packages and generate locking assets:
```bash
make sync
```

### 2. Configure Environment variables
Create a `.env` file at the root:
```bash
cp .env.example .env
```
*(Verify database password in `.env` matches your local PostgreSQL configuration).*

### 3. Spin up Docker Stack
Start Redis, Zookeeper, and Kafka containers:
```bash
docker-compose up -d
```

### 4. Provision PostgreSQL Tables
Initialize the database and tables:
```bash
make init-db
```

### 5. Launch FastAPI Application
Start the reload server:
```bash
make run
```
The documentation will be available at: **`http://127.0.0.1:8000/docs`**

---

## 📖 API Testing Guide
For copy-paste JSON payload samples, header structures, and verification workflows for all API endpoints, check out:
👉 **[docs/testing_payloads.md](file:///c:/Users/hp/Desktop/Granthan/auth-service/docs/testing_payloads.md)**
