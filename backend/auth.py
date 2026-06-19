"""
auth.py — Email/password authentication with JWT
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from memory import get_pool, save_user_preference

security = HTTPBearer(auto_error=False)

JWT_SECRET = os.environ.get("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30


@dataclass
class User:
    id: str
    email: str


async def ensure_users_table() -> None:
    pool = await get_pool()
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            TEXT PRIMARY KEY,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        """
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(user_id: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=JWT_EXPIRE_DAYS)
    payload = {"sub": user_id, "email": email, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def register_user(email: str, password: str, interests: str | None = None) -> User:
    pool = await get_pool()
    user_id = str(uuid.uuid4())
    normalized_email = email.lower().strip()

    try:
        await pool.execute(
            "INSERT INTO users (id, email, password_hash) VALUES ($1, $2, $3)",
            user_id,
            normalized_email,
            hash_password(password),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Email already registered")

    if interests and interests.strip():
        await save_user_preference(user_id, "interests", interests.strip())

    return User(id=user_id, email=normalized_email)


async def authenticate_user(email: str, password: str) -> User | None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, password_hash FROM users WHERE email=$1",
        email.lower().strip(),
    )
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return User(id=row["id"], email=row["email"])


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(security),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        email = payload.get("email", "")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return User(id=user_id, email=email)


async def verify_chat_owner(user_id: str, chat_id: str) -> None:
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT 1 FROM chats WHERE chat_id=$1 AND user_id=$2",
        chat_id,
        user_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Chat not found")
