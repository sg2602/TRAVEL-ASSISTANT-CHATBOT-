# Authentication & Persistent Chat — Change Log

This document lists every file changed to add **email/password login**, **permanent cross-browser chat storage**, and **account-wide interest-based personalization**.

---

## Summary

| Before | After |
|--------|-------|
| Anonymous `user_{uuid}` in `sessionStorage` (tab-scoped) | Real accounts with email + password |
| Client sent `user_id` on every request (no verification) | JWT Bearer token; `user_id` derived from token on server |
| Chats lost when opening a new browser/tab | Chats stored in PostgreSQL under account ID — syncs everywhere |
| Preferences learned only when leaving a chat | Preferences updated after every assistant reply + on session end |
| No login UI | Login / Sign up screen with optional travel interests |

---

## New Files

### `backend/auth.py`
New authentication module.

- **`User`** dataclass — `id`, `email`
- **`ensure_users_table()`** — creates `users` table on app startup (for existing DB volumes)
- **`hash_password()` / `verify_password()`** — bcrypt password hashing
- **`create_access_token()`** — JWT (HS256, 30-day expiry)
- **`register_user()`** — inserts user, optionally saves signup `interests` to `user_profiles`
- **`authenticate_user()`** — email/password login lookup
- **`get_current_user()`** — FastAPI dependency; validates `Authorization: Bearer <token>`
- **`verify_chat_owner()`** — ensures chat belongs to authenticated user

Environment variable: `JWT_SECRET` (defaults to dev secret if unset).

---

### `frontend/src/api.js`
Shared API helper for authenticated requests.

- **`getToken()` / `setToken()` / `clearToken()`** — JWT stored in `localStorage` key `travel_auth_token`
- **`authFetch(path, options)`** — wraps `fetch`, attaches Bearer token, auto-logout on 401
- **`API_URL`** — from `VITE_API_URL` or empty string (uses Vite dev proxy)

---

### `frontend/src/AuthContext.jsx`
React context for auth state.

- **`AuthProvider`** — wraps app, loads user from `/auth/me` on mount
- **`useAuth()`** — hook exposing `{ user, loading, login, register, logout }`
- Listens for `auth:logout` event (dispatched by `authFetch` on 401)

---

### `frontend/src/Login.jsx`
Login / Sign up UI.

- Tab toggle between **Log in** and **Sign up**
- Fields: email, password (min 6 chars)
- Sign up only: optional **Travel interests** text field
- Error display and loading state on submit

---

## Modified Files

### `docker/init.sql`
**Added** `users` table at top of schema:

```sql
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
```

Existing tables (`chats`, `messages`, `chat_summaries`, `user_profiles`) unchanged — they already keyed on `user_id` text, which now maps to `users.id`.

---

### `backend/requirements.txt`
**Added dependencies:**

| Package | Purpose |
|---------|---------|
| `bcrypt` | Password hashing |
| `python-jose[cryptography]` | JWT encode/decode |
| `python-multipart` | Form data support (FastAPI) |
| `email-validator` | Pydantic `EmailStr` validation |

---

### `backend/main.py`
Major rewrite — version bumped to **2.0.0**.

**Added:**
- App `lifespan` handler → calls `ensure_users_table()` on startup
- Auth endpoints: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `Depends(get_current_user)` on all chat and debug routes
- `verify_chat_owner()` before chat-specific operations

**Removed from request bodies / URLs:**
- Client no longer sends `user_id` — server uses authenticated user's ID

**Endpoint changes:**

| Old endpoint | New endpoint |
|--------------|--------------|
| `POST /chat/start` `{ user_id, title }` | `POST /chat/start` `{ title }` + auth |
| `GET /chat/{user_id}/list` | `GET /chat/list` + auth |
| `GET /chat/{user_id}/preferences` | `GET /chat/preferences` + auth |
| `GET /chat/{chat_id}/messages?user_id=` | `GET /chat/{chat_id}/messages` + auth |
| `POST /chat/{chat_id}/message` `{ user_id, message }` | `POST /chat/{chat_id}/message` `{ message }` + auth |
| `POST /chat/{chat_id}/end-session` `{ user_id }` | `POST /chat/{chat_id}/end-session` + auth |
| `DELETE /chat/{chat_id}?user_id=` | `DELETE /chat/{chat_id}` + auth |
| `GET /debug/{user_id}/{chat_id}/memory` | `GET /debug/{chat_id}/memory` + auth |

---

### `backend/memory.py`
**Added** public function:

```python
async def save_user_preference(user_id: str, key: str, value: str) -> None
```

Used by `auth.py` to save signup interests into `user_profiles`.

---

### `backend/agent.py`
**Changed system prompt** — user profile section now says preferences are remembered across **all chats for this account** and the assistant should tailor advice accordingly.

**Added** after each assistant reply:

```python
asyncio.create_task(extract_and_save_preferences(user_id, chat_id))
```

Preferences are now updated continuously, not only when the user leaves a chat.

---

### `docker-compose.yml`
**Added** environment variable to `backend` service:

```yaml
JWT_SECRET: change-this-in-production-use-a-long-random-string
```

---

### `frontend/vite.config.js`
**Added** dev proxy rule:

```js
"/auth": { target: "http://localhost:8000", changeOrigin: true }
```

---

### `frontend/src/main.jsx`
**Changed:**
- Wraps `<App />` in `<AuthProvider>`
- Import path fixed: `"./app"` (Linux/Docker case sensitivity)

---

### `frontend/src/app.jsx`
**Removed:**
- `uuid` import and `getUserId()` / `sessionStorage` logic
- `userId` prop passed to child components
- Direct `fetch()` calls with `user_id` in body/query

**Added:**
- `useAuth()` hook — shows `<Login />` when not authenticated
- Loading spinner while checking existing token
- All API calls via `authFetch()` (no `user_id` in requests)
- Welcome message mentions cross-browser sync and personalized advice
- `userEmail` and `onLogout` passed to `Sidebar`

---

### `frontend/src/chat.jsx`
**Removed:**
- `userId` and `apiUrl` props
- `user_id` from message/end-session request bodies
- `user_id` query param from messages fetch

**Changed:**
- All requests use `authFetch()` from `./api`
- Component only needs `chatId` and `onTitleUpdate` props

---

### `frontend/src/Sidebar.jsx`
**Removed:**
- `userId` prop, `apiUrl` prop
- Raw `fetch()` for preferences

**Added:**
- `userEmail` prop — shows logged-in email in footer
- `onLogout` prop — **Log out** button
- Preferences fetched via `authFetch("/chat/preferences")`

---

### `frontend/src/index.css`
**Added styles for:**
- `.auth-screen`, `.auth-card`, `.auth-tabs`, `.auth-form`, `.auth-input`, `.auth-error`, `.auth-submit`
- `.btn-logout` in sidebar footer
- Updated `.sidebar-footer` to flex layout (email + logout button)

---

## Unchanged Files (still relevant)

| File | Role |
|------|------|
| `backend/tools.py` | Travel tools (weather, places, country) — no auth changes |
| `backend/test_memory.py` | Memory tests — still use raw `user_id` strings |
| `backend/test_agent.py` | Agent tests — unchanged |
| `frontend/src/MemoryBadge.jsx` | Preference count badge — unchanged |
| `docker/init.sql` (rest) | `chats`, `messages`, `chat_summaries`, `user_profiles` tables unchanged |

---

## Data Flow (After Changes)

```
1. User signs up / logs in
   → POST /auth/register or /auth/login
   → JWT returned → stored in localStorage

2. User opens app on any browser
   → GET /auth/me with Bearer token
   → Same account → same chats

3. User sends a message
   → POST /chat/{chat_id}/message (auth required)
   → Backend loads user_profiles for that account
   → Agent system prompt includes interests/preferences
   → Response streamed via SSE
   → Preferences re-extracted in background

4. User logs out
   → Token cleared from localStorage
   → Redirected to login screen
```

---

## Migration Notes

- **Existing anonymous chats** (from old `sessionStorage` user IDs) are **not** linked to new accounts. Only chats created after sign-up belong to the account.
- **Existing PostgreSQL volumes** get the `users` table via `ensure_users_table()` on backend startup — no manual migration needed.
- **Rebuild / restart** after pulling these changes:

  ```powershell
  docker compose down
  docker compose up --build
  ```

  Or, if containers are already running:

  ```powershell
  docker exec travel_backend pip install bcrypt python-jose[cryptography] python-multipart email-validator
  docker restart travel_backend
  ```

---

## Security Notes (for production)

- Set a strong `JWT_SECRET` in production (not the docker-compose default).
- Tighten CORS `allow_origins` in `main.py`.
- Move API keys out of `docker-compose.yml` into `.env` only.
- Consider httpOnly cookies instead of localStorage for JWT storage.
