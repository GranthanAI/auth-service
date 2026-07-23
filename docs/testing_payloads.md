# Swagger API Testing Payloads Guide

This document lists every endpoint implemented in the **Granthan Auth Service** along with its HTTP method, header/cookie requirements, and complete request/response JSON payloads for testing in the Swagger UI (`http://127.0.0.1:8000/docs`).

---

## 1. Registration & Verification Flows (Public)

### 1.1 Register User Account
* **Endpoint:** `POST /auth/register`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "email": "shubh@gmail.com",
    "password": "Shubh123@ABCD",
    "full_name": "Soubhagya Srivastava"
  }
  ```
* **Response JSON (201 Created):**
  ```json
  {
    "id": "27131a6e-0267-49cd-ab5a-5955a423d505",
    "email": "shubh@gmail.com",
    "full_name": "Soubhagya Srivastava",
    "avatar_url": null,
    "is_email_verified": false,
    "status": "PENDING",
    "created_at": "2026-07-23T19:00:00Z",
    "updated_at": "2026-07-23T19:00:00Z",
    "last_login": null
  }
  ```
  *(Note: A 6-digit numeric verification OTP is printed to the uvicorn terminal console immediately upon calling this endpoint).*

### 1.2 Verify Email OTP
* **Endpoint:** `POST /auth/verify-email`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "email": "shubh@gmail.com",
    "code": "123456"
  }
  ```
  *(Replace `123456` with the OTP printed to the console).*
* **Response JSON (200 OK):**
  ```json
  {
    "message": "Email address verified successfully. Your account is now active."
  }
  ```

### 1.3 Resend Verification OTP
* **Endpoint:** `POST /auth/resend-verification`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "email": "shubh@gmail.com"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "message": "A new verification code has been generated and printed to the developer console."
  }
  ```

---

## 2. Authentication & Session Flows (Public)

### 2.1 Login Account
* **Endpoint:** `POST /auth/login`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "email": "shubh@gmail.com",
    "password": "Shubh123@ABCD"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```
  *(Note: Sets a secure, HTTP-only `refresh_token` cookie in your browser headers).*

### 2.2 Rotate Tokens (Refresh)
* **Endpoint:** `POST /auth/refresh`
* **Browser Requirement:** Automatically attaches the `refresh_token` cookie set during login. If using curl or postman, attach the cookie header:
  `Cookie: refresh_token=<token_hex_string>`
* **Request JSON Body:** *None (Send empty body or raw POST request)*
* **Response JSON (200 OK):**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 900
  }
  ```
  *(Note: Rotates the `refresh_token` and updates the secure cookie dynamically).*

### 2.3 Logout Account
* **Endpoint:** `POST /auth/logout`
* **Browser Requirement:** Automatically attaches the `refresh_token` cookie.
* **Request JSON Body:** *None*
* **Response JSON (200 OK):**
  ```json
  {
    "message": "Logged out successfully."
  }
  ```
  *(Note: Deletes the `refresh_token` cookie and revokes the active session in PostgreSQL).*

---

## 3. Account Recovery (Public)

### 3.1 Request Password Reset (Forgot Password)
* **Endpoint:** `POST /auth/forgot-password`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "email": "shubh@gmail.com"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "message": "Password reset token generated and printed to the developer console."
  }
  ```
  *(Note: A cryptographically secure recovery token is printed to your uvicorn terminal console).*

### 3.2 Reset Password with Token
* **Endpoint:** `POST /auth/reset-password`
* **Headers:** `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "token": "raw-token-from-terminal-console",
    "new_password": "NewShubhPassword123@!"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "message": "Password reset successfully. All active sessions have been logged out."
  }
  ```

---

## 4. Protected API Flows (Requires Authentication JWT)

> [!IMPORTANT]
> To access any endpoints in this section, you must copy the `access_token` returned by `POST /auth/login`. In Swagger UI, click **Authorize** at the top-right, paste the JWT string into the token value input field, and click **Authorize**. This attaches the token automatically as the `Authorization: Bearer <JWT>` header.

### 4.1 Fetch Current User Profile
* **Endpoint:** `GET /auth/me`
* **Headers:** `Authorization: Bearer <access_token>`
* **Request Body:** *None*
* **Response JSON (200 OK):**
  ```json
  {
    "id": "27131a6e-0267-49cd-ab5a-5955a423d505",
    "email": "shubh@gmail.com",
    "full_name": "Soubhagya Srivastava",
    "avatar_url": null,
    "is_email_verified": true,
    "status": "ACTIVE",
    "created_at": "2026-07-23T19:00:00Z",
    "updated_at": "2026-07-23T19:02:00Z",
    "last_login": "2026-07-23T19:05:00Z"
  }
  ```

### 4.2 Update Profile
* **Endpoint:** `PATCH /auth/profile`
* **Headers:** `Authorization: Bearer <access_token>`, `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "full_name": "Shubh Srivastava",
    "avatar_url": "https://avatars.githubusercontent.com/u/123456"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "id": "27131a6e-0267-49cd-ab5a-5955a423d505",
    "email": "shubh@gmail.com",
    "full_name": "Shubh Srivastava",
    "avatar_url": "https://avatars.githubusercontent.com/u/123456",
    "is_email_verified": true,
    "status": "ACTIVE",
    "created_at": "2026-07-23T19:00:00Z",
    "updated_at": "2026-07-23T19:10:00Z",
    "last_login": "2026-07-23T19:05:00Z"
  }
  ```

### 4.3 Change Password
* **Endpoint:** `POST /auth/change-password`
* **Headers:** `Authorization: Bearer <access_token>`, `Content-Type: application/json`
* **Request JSON Body:**
  ```json
  {
    "old_password": "Shubh123@ABCD",
    "new_password": "ChangedShubhPassword123@!"
  }
  ```
* **Response JSON (200 OK):**
  ```json
  {
    "message": "Password changed successfully."
  }
  ```
