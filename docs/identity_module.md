# Identity Module Design Document

The **Identity Module** is the foundational subsystem of the Granthan Auth Service. It manages the lifecycle, storage, validation, and retrieval of user account information.

---

## 1. Module Overview & Responsibilities

The Identity Module maintains user profiles and provides services to create, retrieve, and update user records. It acts as the gateway to the core user identity for other authentication modules (e.g., Password, Session, and Verification Modules).

### Core Features
* **User Registration:** Provisioning new accounts in a `PENDING` state.
* **Identity Lookup:** Fast retrieval of user details by `id` or `email` (e.g., during login, password recovery, or profile fetch).
* **Profile Management:** Modifying non-sensitive user attributes (full name, avatar URL).
* **Email Lifecycle:** Safely updating email addresses and coordinating email verification status.

---

## 2. File and Component Responsibilities

The module is implemented across the following layers:

| Layer | File Path | Class / Function | Responsibility |
| :--- | :--- | :--- | :--- |
| **Model** | [app/models/user.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/models/user.py) | `User` | Maps identity to the `users` table in PostgreSQL. |
| **Repository** | [app/repositories/user_repository.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/repositories/user_repository.py) | `UserRepository` | Handles database queries and raw database writes. |
| **Service** | [app/services/user_service.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/services/user_service.py) | `UserService` | Orchestrates password checks, user state transitions, and raises business exceptions. |
| **Router (API)** | [app/api/routers/users.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/api/routers/users.py) | `GET /auth/me`, `PATCH /auth/profile` | Exposes identity management actions to authenticated users. |
| **Router (Auth)** | [app/api/routers/auth.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/api/routers/auth.py) | `POST /auth/register` | Exposes the registration entry point. |
| **Schemas** | [app/api/schemas/user.py](file:///c:/Users/hp/Desktop/Granthan/auth-service/app/api/schemas/user.py) | `UserResponse`, `ProfileUpdate` | Declares input/output Pydantic structure and data validation rules. |

---

## 3. Database Schema: The `users` Table

* **SQLAlchemy Class:** `User` in `app/models/user.py`
* **Table Fields & Details:**

```python
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.core.enums import UserStatus  # PENDING, ACTIVE, SUSPENDED

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    full_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus), default=UserStatus.PENDING, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

---

## 4. Repository Layer (`UserRepository`)

The repository handles database transactions via `SQLAlchemy` async queries.

### Operations Contract:
* `async def get_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None`:
  Retrieves a user by primary key. Used by the authentication middleware to fetch the current user payload from the JWT `sub` claim.
* `async def get_by_email(db: AsyncSession, email: str) -> User | None`:
  Looks up a user by email address (forces input to lowercase). Used to prevent duplicate email registrations and locate user records during credentials checking.
* `async def create(db: AsyncSession, user_in: UserCreate, hashed_password: str) -> User`:
  Inserts a new user record. Sets default status to `PENDING`.
* `async def update(db: AsyncSession, user_obj: User, updates: dict) -> User`:
  Applies incremental column changes (e.g. updating profile details or logging in).

---

## 5. Service Layer Logic (`UserService`)

The service coordinates multiple domain-level policies.

### 5.1 Registration Flow Details
When a registration request (`RegisterRequest`) is received:
1. **Uniqueness Check:** Calls `UserRepository.get_by_email(email)`. If a record is found, it raises `UserAlreadyExistsException` (maps to HTTP 409 Conflict).
2. **Password Validation:** Validates strength guidelines via `app/security/validators.py` before executing any writes.
3. **Hashing:** Uses `PasswordHasher.hash(password)` to compute the Argon2id hash. The plain text password is never stored or logged.
4. **Persistence:** Calls `UserRepository.create(...)` to save the user record with `status=PENDING` and `is_email_verified=FALSE`.
5. **Transactional Event Queueing:** Generates email verification parameters and writes them to PostgreSQL alongside the transactional outbox event inside the *same* database transaction block.

### 5.2 Email Verification & Status Changes
* When the Verification Module validates a correct verification OTP:
  * The `UserService` marks `is_email_verified = True` and sets the user status to `ACTIVE`.
  * These state updates allow the user to perform login queries.

---

## 6. API Validation & Data Schemas

Pydantic schemas enforce type restrictions, length thresholds, and format patterns at the entry gate.

```python
# app/api/schemas/user.py
import re
from pydantic import BaseModel, EmailStr, Field, field_validator

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    full_name: str | None = Field(None, min_length=2, max_length=100)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # Rules: At least 1 uppercase, 1 lowercase, 1 digit, 1 special character
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    avatar_url: str | None
    is_email_verified: bool
    status: UserStatus
    created_at: datetime

    class Config:
        from_attributes = True

class ProfileUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=100)
    avatar_url: str | None = Field(None, max_length=1024)
```

---

## 7. Endpoint Contracts

### 7.1 Fetch Current User: `GET /auth/me`
Retrieves information about the currently logged-in user context.
* **Authentication Required:** Yes (Valid Access JWT in header).
* **Process Flow:**
  1. Middleware extracts and verifies the bearer token.
  2. Extracts the `sub` claim.
  3. `UserService.get_user_by_id(sub)` returns the user model.
  4. Serialized as `UserResponse`.
* **Response (HTTP 200 OK):**
  ```json
  {
    "id": "c92a9c37-88f2-4933-bf9c-29a32c25368a",
    "email": "user@example.com",
    "full_name": "Alice Smith",
    "avatar_url": "https://cdn.granthan.com/avatars/alice.png",
    "is_email_verified": true,
    "status": "ACTIVE",
    "created_at": "2026-07-23T13:00:00Z"
  }
  ```

### 7.2 Update Profile: `PATCH /auth/profile`
Updates profile properties of the current user.
* **Authentication Required:** Yes.
* **Request Payload:** `ProfileUpdate` (only non-empty fields are patched).
* **Response (HTTP 200 OK):**
  * Returns the updated `UserResponse` object.
* **Audit Event:** Triggers an audit record: `USER_PROFILE_UPDATED` containing the updated fields inside metadata.
