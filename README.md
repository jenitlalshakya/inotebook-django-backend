# iNotebook Backend

Django-based REST API backend for the **iNotebook** secure note-taking application.  
This backend handles authentication, encrypted note storage, subscription management, and file uploads, communicating with a **MongoDB** database (no Django ORM / SQL used).

---

## Features

- **JWT Authentication** — stateless login/signup with HS256-signed tokens; 1-day expiry.
- **Bcrypt + Pepper password hashing** — passwords are salted, hashed, and peppered before storage.
- **Token invalidation on password change** — tokens issued before a password change are automatically rejected.
- **Automatic subscription expiry** — on every authenticated request, expired paid plans are silently reverted to Free.
- **End-to-end note encryption** — note content, titles, and tags are encrypted at rest using a symmetric key; decryption happens in memory only.
- **Paginated notes listing** — `limit` / `skip` query parameters for infinite scroll support.
- **Advanced note search** — field-scoped (`title:`, `content:`, `tag:`), comma-separated AND conditions, and `or` groups; search runs over decrypted data in memory.
- **Soft-delete / Trash system** — notes are soft-deleted into a trash bin; they can be restored or permanently deleted.
- **Favorites** — notes can be marked/unmarked as favorites and fetched separately.
- **Subscription plans** — Free, Pro Monthly (₹299/30 days), and Pro Yearly (₹2,999/365 days).
- **Plan limits enforcement** — Free users are limited to 50 notes and 500 words per note; enforced on create and update.
- **eSewa sandbox payment integration** — HMAC-SHA256 signed payment initiation and server-side signature verification on callback (demo/sandbox only).
- **File upload system** — Pro users can upload files (stored on disk); per-user storage tracked and enforced (5 GB limit).
- **File management** — list and delete uploaded files; storage counter is updated on deletion.
- **CORS configured** — `django-cors-headers` restricts cross-origin requests to the configured frontend origin.
- **Media file serving** — uploaded files are served via Django's static media serving in development.

---

## Tech Stack

| Component | Technology |
|---|---|
| Framework | Django 6.0.2 |
| Database | MongoDB (via PyMongo 4.x) |
| Authentication | PyJWT (HS256), Bcrypt |
| Data validation | Pydantic v2 |
| Encryption | `cryptography` (AES-GCM / symmetric) |
| CORS | django-cors-headers |
| Environment | python-dotenv |
| Payment | eSewa ePay v2 (sandbox) |
| WSGI server | Gunicorn (production) |
| Python | 3.x |

---

## Project Structure

```text
backend/
│
├── config/                 # Django project settings, root URLs, WSGI/ASGI
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
│
├── accounts/               # Authentication app
│   ├── views.py            # signup, login, profile, change_password, delete_account
│   ├── urls.py
│   └── utils.py            # jwt_required decorator + subscription expiry logic
│
├── notes/                  # Notes management app
│   ├── views.py            # CRUD, search, trash, restore, favorites
│   └── urls.py
│
├── subscription/           # Subscription & payment app
│   ├── views.py            # plan configs, eSewa payment initiation & callbacks
│   └── urls.py
│
├── files/                  # File upload app (Pro users only)
│   ├── views.py            # upload, list, delete
│   └── urls.py
│
├── core/                   # Shared utilities
│   ├── mongo.py            # MongoDB connection & collection handles
│   ├── schema/
│   │   ├── User_Schema.py
│   │   ├── Note_Schema.py
│   │   └── File_Schema.py
│   └── utils/
│       └── encryption.py   # encrypt_text / decrypt_text helpers
│
├── template/               # Django HTML templates
│   └── subscription_form.html   # eSewa POST form (auto-submits to sandbox)
│
├── media/                  # Uploaded files (created at runtime, gitignored)
├── requirements.txt
├── manage.py
└── .env                    # Environment variables (not committed)
```

---

## Database Collections (MongoDB)

### `users`
| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Primary key (auto) |
| `name` | str | Display name |
| `email` | str | Unique, indexed |
| `password` | str | Bcrypt + pepper hash |
| `plan` | str | `"free"` / `"pro_monthly"` / `"pro_yearly"` |
| `subscription_type` | str? | `"esewa"` when set |
| `subscription_start` | datetime? | Plan activation date |
| `subscription_end` | datetime? | Plan expiry date |
| `storage_used` | int | Bytes used by uploaded files |
| `password_changed_at` | datetime? | Used to invalidate old tokens |
| `created_at` / `updated_at` | datetime | Timestamps |

### `notes`
| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Primary key (auto) |
| `user_id` | ObjectId | Owner reference |
| `title` | str | **Encrypted** at rest |
| `content` | str | **Encrypted** at rest |
| `tag` | str | **Encrypted** at rest |
| `is_deleted` | bool | Soft-delete flag (trash) |
| `is_favorite` | bool | Favorite flag |
| `created_at` / `updated_at` | datetime | Timestamps |

### `files`
| Field | Type | Description |
|---|---|---|
| `_id` | ObjectId | Primary key (auto) |
| `user_id` | ObjectId | Owner reference |
| `file_name` | str | Original filename |
| `file_size` | int | File size in bytes |
| `file_type` | str | MIME type |
| `file_url` | str | Relative media URL path |
| `created_at` | datetime | Upload timestamp |

---

## API Endpoints

All API routes are prefixed with `/api/`.  
Protected routes require the `Authorization: Bearer <token>` header.

### Authentication — `/api/accounts/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `auth/signup/` | No | Register a new user |
| POST | `auth/login/` | No | Login; returns JWT token + name |
| GET | `auth/profile/` | Yes | Get profile (name, email, plan, storage, sub expiry) |
| POST | `auth/change-password/` | Yes | Change password (old + new required) |
| DELETE | `auth/delete-account/` | Yes | Delete account and all associated notes |

### Notes — `/api/notes/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `create/` | Yes | Create a note (encrypted; plan limits enforced) |
| GET | `all/` | Yes | List notes (`?limit=&skip=`); excludes deleted & favorites |
| GET | `search/` | Yes | Search notes (`?q=`); supports field scoping and OR groups |
| PUT | `update/<note_id>/` | Yes | Update note fields (word limit enforced for Free users) |
| DELETE | `delete/<note_id>/` | Yes | Soft-delete (move to trash) |
| GET | `get-trash/` | Yes | List trashed notes |
| POST | `restore/<note_id>/` | Yes | Restore a note from trash |
| DELETE | `delete-permanent/<note_id>/` | Yes | Permanently delete a trashed note |
| DELETE | `empty-trash/` | Yes | Permanently delete **all** trashed notes |
| PUT | `favorite/<note_id>/` | Yes | Mark note as favorite |
| PUT | `unfavorite/<note_id>/` | Yes | Remove note from favorites |
| GET | `favorites/` | Yes | List all favorite notes |

### Subscription — `/api/subscription/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| GET | `configs` | No | Returns PLANS config (limits, prices, durations) |
| GET | `payment/` | Yes | Initiate eSewa payment; renders sandbox POST form |
| GET | `success` | No | eSewa success callback; verifies signature, activates plan |
| GET | `failure` | No | eSewa failure/cancel callback; shows error page |

### Files — `/api/files/`

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `upload` | Yes (Pro) | Upload a file; checks storage quota |
| GET | `list` | Yes | List all uploaded files for the user |
| DELETE | `delete/<file_id>` | Yes | Delete a file; frees storage |

> **Note:** File upload is blocked for Free plan users with a `403` response.

---

## Subscription Plans

| | Free | Pro Monthly | Pro Yearly |
|---|---|---|---|
| Price | ₹0 | ₹299 | ₹2,999 |
| Duration | — | 30 days | 365 days |
| Notes | Up to 50 | Unlimited | Unlimited |
| Words per note | 500 | Unlimited | Unlimited |
| File uploads | ✗ | ✓ | ✓ |
| Storage | — | 5 GB | 5 GB |

---

## Payment Flow (eSewa Sandbox)

> **⚠️ Demo / Sandbox Only — No real money is charged.**  
> Use [eSewa sandbox test credentials](https://developer.esewa.com.np/) during checkout.

### 🧪 Sandbox Test Credentials
eSewa Test Accounts:
- 9806800001
- 9806800002
- 9806800003
- 9806800004
- 9806800005

**Credentials for all sandbox accounts:**
- Password: Nepal@123
- MPIN: 1122
- OTP: 123456

> ⚠️ These credentials are for eSewa sandbox only. Do not use them for real transactions.

```
Frontend  ──GET /api/subscription/payment/?plan=pro_monthly──▶  Backend
   ◀── renders subscription_form.html (auto-POST to eSewa sandbox)
        │
        ▼  (browser redirects to eSewa sandbox)
   User completes sandbox checkout
        │
        ▼  (eSewa redirects back with base64-encoded JSON)
Backend  ◀──GET /api/subscription/success?data=<base64>──
   1. Decode and parse eSewa response JSON
   2. Reconstruct HMAC-SHA256 message from signed_field_names
   3. Compare expected vs received signature → reject on mismatch
   4. Verify status == "COMPLETE"
   5. Extract user_id from transaction_uuid prefix
   6. Infer plan from amount (₹299 → pro_monthly, ₹2999 → pro_yearly)
   7. Write plan, subscription_type, start/end dates to users collection
   8. Redirect browser to frontend /profile page
```

On failure or cancellation, eSewa redirects to `/api/subscription/failure`, which shows an error page with a link back to the upgrade page. No database changes are made.

---

## Authentication & Security Details

- **JWT**: HS256, 1-day expiry. Secret read from `JWT_SECRET` env var.
- **Password hashing**: `bcrypt` with a server-side pepper (`PASSWORD_PEPPER`). Old tokens are rejected if a password change occurred after token issuance.
- **Subscription expiry**: Checked on every protected request via the `jwt_required` decorator. Expired paid plans are automatically downgraded to Free in MongoDB.
- **Note encryption**: All note fields (`title`, `content`, `tag`) are encrypted before write and decrypted after read using a symmetric key (`ENCRYPTION_KEY`). The database never stores plaintext note content.

---

## Installation & Setup

### Prerequisites

- **Python 3.10+**
- **pip** and **virtualenv** (or equivalent)
- A running **MongoDB** instance (local or MongoDB Atlas)

### 1. Clone the repository

```bash
git clone https://github.com/jenitlalshakya/inotebook.git
cd inotebook-django/backend
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the `backend/` directory:

```env
# Django
DJANGO_SECRET_KEY=your-django-secret-key
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# MongoDB
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority

# JWT & Security
JWT_SECRET=your-jwt-secret
PASSWORD_PEPPER=your-pepper-string
ENCRYPTION_KEY=your-AES-GCM-encryption-key

# Frontend origin (for CORS and payment redirect)
FRONTEND_URL=http://localhost:5173

# eSewa Sandbox Credentials
ESEWA_SECRET_KEY=8gBm/:&EnhH.1/q   # default sandbox secret key
ESEWA_PRODUCT_CODE=EPAYTEST         # default sandbox product code
```

> **Tip:** Generate a valid AES-GCM (256-bit) key with:
> ```python
> from cryptography.hazmat.primitives.ciphers.aead import AESGCM
> import base64
>
> key = AESGCM.generate_key(bit_length=256)
> print(base64.b64encode(key).decode())
> ```

---

## Running the Development Server

```bash
python manage.py runserver
```

The API will be available at:

```
http://127.0.0.1:8000
```

> **No `migrate` required.** This project does not use Django's ORM or SQL database. MongoDB collections and indexes are created automatically on first connection.

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | Yes | Django secret key for session signing |
| `DEBUG` | Yes | `True` for development, `False` for production |
| `ALLOWED_HOSTS` | Yes | Comma-separated list of allowed hostnames |
| `MONGO_URI` | Yes | Full MongoDB connection string (SRV or standard) |
| `JWT_SECRET` | Yes | Secret used to sign and verify JWT tokens |
| `PASSWORD_PEPPER` | Yes | Server-side pepper appended to passwords before hashing |
| `ENCRYPTION_KEY` | Yes | Base64-encoded 32-byte key for AES-GCM (AES-256) note encryption |
| `FRONTEND_URL` | Yes | Frontend origin (e.g. `http://localhost:5173`); used for CORS and payment redirect |
| `ESEWA_SECRET_KEY` | Yes | eSewa sandbox HMAC secret key |
| `ESEWA_PRODUCT_CODE` | Yes | eSewa sandbox product code (`EPAYTEST` for sandbox) |

---

## Production Deployment Notes

- Set `DEBUG=False` and restrict `ALLOWED_HOSTS`.
- Use **Gunicorn** (`gunicorn config.wsgi:application`) as the WSGI server.
- Serve `media/` files through a proper web server (Nginx / CDN) — Django's `static()` shortcut is development-only.
- MongoDB Atlas (free tier) works well for cloud deployments.
- Ensure `FRONTEND_URL` matches your deployed frontend domain for CORS and payment redirects.

---

## Future Improvements

- **Email verification** on signup.
- **Password reset** via email (OTP or reset link).
- **Production payment gateway** — replace eSewa sandbox with live credentials, or integrate Stripe/Razorpay.
- **Note sharing** between users.
- **Note tags / categories** with filtering.
- **Rate limiting** on auth endpoints to prevent brute-force.
- **Refresh tokens** for extended sessions without re-login.
- **Admin dashboard** for user and subscription management.

---

## Author

**Jenit Lal Shakya**

If you find this project useful, feel free to star it on GitHub or open issues/PRs with suggestions and improvements.
