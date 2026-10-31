import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

load_dotenv()
BASE = Path(__file__).resolve().parent
PUBLIC = BASE / "public"
APP_ENV = os.getenv("APP_ENV", "development").lower()
PRODUCTION = APP_ENV == "production"
LOCAL_DEMO = APP_ENV == "local-demo"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_SQLITE = not PRODUCTION
if PRODUCTION and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required in production. Check the Render PostgreSQL connection setting.")
LOCAL_DB = BASE / "vinedu-local.db"

app = Flask(__name__, static_folder=None)
if USE_SQLITE:
    class SQLiteConnection:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, statement, params=()):
            return self.connection.execute(statement.replace("%s", "?"), params)

        def executescript(self, statement):
            return self.connection.executescript(statement)

    class SQLitePool:
        @contextmanager
        def connection(self):
            connection = sqlite3.connect(LOCAL_DB, timeout=30)
            connection.row_factory = sqlite3.Row
            try:
                yield SQLiteConnection(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    pool = SQLitePool()
else:
    pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8,
                          kwargs={"row_factory": dict_row, "sslmode": "require" if PRODUCTION else "prefer"}, open=False)
limits = {}
limits_lock = threading.Lock()
SESSION_DAYS = 14
DEFAULT_DATA = {"progress": {}, "completed": [], "bookmarks": [], "activity": [], "attempts": {},
                "enrolled": [], "assignments": [], "meetings": [],
                "customCourses": [], "notes": [], "planner": [], "flashcards": [], "settings": {}}


def hash_password(password):
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return f"scrypt$16384$8$1${salt.hex()}${derived.hex()}"


def verify_password(password, stored):
    try:
        algo, n, r, p, salt, expected = stored.split("$")
        if (algo, int(n), int(r), int(p)) != ("scrypt", 2**14, 8, 1):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=64)
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def initialize_database():
    pool.open(wait=True)
    with pool.connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student'
                  CHECK (role IN ('student','admin')),
                is_blocked BOOLEAN NOT NULL DEFAULT FALSE,
                profile_photo BYTEA,
                profile_photo_type TEXT,
                learning_data JSONB NOT NULL DEFAULT '{"progress":{},"completed":[],"bookmarks":[],"activity":[],"attempts":{},"enrolled":[],"assignments":[],"meetings":[],"customCourses":[],"notes":[],"planner":[],"settings":{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS course_catalog (
                course_id TEXT PRIMARY KEY, course_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                is_deleted BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS users_created_at_idx ON users(created_at);
        """)
        conn.execute("DELETE FROM sessions WHERE expires_at<NOW()")
    provision_admin()


def provision_admin():
    email = (os.getenv("ADMIN_EMAIL") or os.getenv("DEMO_ADMIN_EMAIL", "")).strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or os.getenv("DEMO_ADMIN_PASSWORD", "")
    if not email and not password:
        if PRODUCTION:
            raise RuntimeError("Set ADMIN_EMAIL and ADMIN_PASSWORD as private Render environment variables.")
        return
    if not email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise RuntimeError("ADMIN_EMAIL must be a valid email address.")
    minimum = 16 if PRODUCTION else 8
    if len(password) < minimum:
        raise RuntimeError(f"Admin password must have at least {minimum} characters.")
    name = os.getenv("ADMIN_NAME", "Vinedu Administrator").strip()[:80]
    # Keep the configured Render admin password synchronized with the database.
    # Existing student accounts are never promoted to admin by this upsert.
    with pool.connection() as conn:
        conn.execute("""
            INSERT INTO users(email,display_name,password_hash,role)
            VALUES(%s,%s,%s,'admin')
            ON CONFLICT(email) DO UPDATE SET
                display_name=EXCLUDED.display_name,
                password_hash=EXCLUDED.password_hash,
                updated_at=CURRENT_TIMESTAMP
            WHERE users.role='admin'
        """, (email, name, hash_password(password)))
        account = conn.execute("SELECT role FROM users WHERE email=%s", (email,)).fetchone()
        if not account or account["role"] != "admin":
            raise RuntimeError(
                "ADMIN_EMAIL is already assigned to a non-admin account. "
                "Set ADMIN_EMAIL to a separate administrator email."
            )


def api_body():
    if request.content_length and request.content_length > 3_000_000:
        raise ValueError("Request too large.")
    return request.get_json(silent=True) or {}


def same_origin():
    if request.headers.get("Sec-Fetch-Site") == "cross-site":
        return False
    origin = request.headers.get("Origin")
    if not origin:
        return True
    try:
        return origin.split("://", 1)[-1].split("/", 1)[0] == request.host
    except (AttributeError, IndexError):
        return False


def rate_limited():
    key, now = (request.remote_addr or "unknown", request.path), time.time()
    with limits_lock:
        count, start = limits.get(key, (0, now))
        if now - start > 900:
            count, start = 0, now
        count += 1
        limits[key] = (count, start)
        return count > 12


def current_user():
    token = request.cookies.get("vinedu_session", "")
    if not token or len(token) > 100:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with pool.connection() as conn:
        expiry_clause = "s.expires_at>CURRENT_TIMESTAMP AND u.is_blocked=FALSE" if USE_SQLITE else "s.expires_at>NOW() AND u.is_blocked=FALSE"
        return conn.execute(f"""
            SELECT u.id,u.email,u.display_name,u.role,u.learning_data,(u.profile_photo_type IS NOT NULL) AS has_photo FROM sessions s
            JOIN users u ON u.id=s.user_id WHERE s.token_hash=%s AND s.expires_at>NOW() AND u.is_blocked=FALSE
        """.replace("s.expires_at>NOW()", expiry_clause), (token_hash,)).fetchone()


def user_json(user):
    data = user["learning_data"] or DEFAULT_DATA
    if isinstance(data, str):
        data = json.loads(data)
    has_photo = "has_photo" in user.keys() and bool(user["has_photo"])
    return {"id": user["id"], "email": user["email"], "name": user["display_name"], "role": user["role"], "hasPhoto": has_photo, **data}


def session_response(payload, user_id, status=200):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with pool.connection() as conn:
        expiry_sql = "datetime('now','+14 days')" if USE_SQLITE else "NOW()+INTERVAL '14 days'"
        conn.execute(f"INSERT INTO sessions(token_hash,user_id,expires_at) VALUES(%s,%s,{expiry_sql})", (token_hash, user_id))
    response = jsonify(payload)
    response.status_code = status
    response.set_cookie("vinedu_session", token, max_age=SESSION_DAYS * 86400,
                        httponly=True, secure=PRODUCTION, samesite="Lax", path="/")
    return response


@app.get("/")
def home():
    return send_from_directory(PUBLIC, "index.html")


@app.get("/<path:filename>")
def static_asset(filename):
    return send_from_directory(PUBLIC, filename)


@app.get("/api/config")
def config():
    # Demo credentials are only exposed when the developer opts into local-demo mode.
    demo = None
    email, password = os.getenv("DEMO_ADMIN_EMAIL"), os.getenv("DEMO_ADMIN_PASSWORD")
    if LOCAL_DEMO and email and password:
        with pool.connection() as conn:
            account = conn.execute("SELECT password_hash FROM users WHERE email=%s AND role='admin'", (email.strip().lower(),)).fetchone()
        demo = {"email": email,
                "password": password if account and verify_password(password, account["password_hash"]) else "(updated; use the new password you set)",
                "resetToken": os.getenv("DEMO_ADMIN_RESET_TOKEN", "local-demo-reset-code-change-me")}
    return jsonify(demoAdmin=demo)


@app.get("/api/me")
def me():
    user = current_user()
    return jsonify(user=user_json(user) if user else None)


@app.get("/api/profile/photo")
def profile_photo():
    user = current_user()
    if not user:
        return jsonify(error="Please log in to view this photo."), 401
    with pool.connection() as conn:
        photo = conn.execute("SELECT profile_photo,profile_photo_type FROM users WHERE id=%s", (user["id"],)).fetchone()
    if not photo or not photo["profile_photo"] or photo["profile_photo_type"] not in ("image/jpeg", "image/png", "image/webp"):
        return jsonify(error="No profile photo."), 404
    response = send_file(io.BytesIO(photo["profile_photo"]), mimetype=photo["profile_photo_type"], max_age=0, download_name="profile-photo")
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.post("/api/profile/photo")
def save_profile_photo():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in first."), 401
    body = api_body()
    if body.get("remove") is True:
        with pool.connection() as conn:
            conn.execute("UPDATE users SET profile_photo=NULL,profile_photo_type=NULL,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (user["id"],))
        return jsonify(ok=True, hasPhoto=False)
    value = str(body.get("data", ""))
    match = re.fullmatch(r"data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)", value)
    if not match:
        return jsonify(error="Choose a JPEG, PNG or WebP photo."), 400
    mime, encoded = match.groups()
    try:
        photo = base64.b64decode(encoded, validate=True)
    except ValueError:
        return jsonify(error="The selected photo could not be read."), 400
    if not photo or len(photo) > 2 * 1024 * 1024:
        return jsonify(error="Profile photos must be smaller than 2 MB."), 413
    valid = (mime == "image/jpeg" and photo.startswith(b"\xff\xd8\xff")) or (mime == "image/png" and photo.startswith(b"\x89PNG\r\n\x1a\n")) or (mime == "image/webp" and photo.startswith(b"RIFF") and photo[8:12] == b"WEBP")
    if not valid:
        return jsonify(error="Photo file type does not match its image data."), 400
    with pool.connection() as conn:
        conn.execute("UPDATE users SET profile_photo=%s,profile_photo_type=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (photo, mime, user["id"]))
    return jsonify(ok=True, hasPhoto=True)


@app.post("/api/register")
def register():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    if rate_limited():
        return jsonify(error="Too many attempts. Please wait and try again."), 429
    body = api_body()
    email = str(body.get("email", "")).strip().lower()
    name, password = str(body.get("name", "")).strip(), str(body.get("password", ""))
    if len(name) < 2 or len(name) > 80 or len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify(error="Enter your name and a valid email address."), 400
    if not 12 <= len(password) <= 128:
        return jsonify(error="Use a password between 12 and 128 characters."), 400
    try:
        with pool.connection() as conn:
            user = conn.execute("""
                INSERT INTO users(email,display_name,password_hash) VALUES(%s,%s,%s)
                RETURNING id,email,display_name,role,learning_data,(profile_photo_type IS NOT NULL) AS has_photo
            """, (email, name, hash_password(password))).fetchone()
    except (psycopg.errors.UniqueViolation, sqlite3.IntegrityError):
        return jsonify(error="An account already exists for that email. Please log in instead."), 409
    return session_response({"user": user_json(user)}, user["id"], 201)


@app.post("/api/login")
def login():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    if rate_limited():
        return jsonify(error="Too many attempts. Please wait and try again."), 429
    body = api_body()
    email, password = str(body.get("email", "")).strip().lower(), str(body.get("password", ""))
    role = "admin" if body.get("role") == "admin" else "student"
    with pool.connection() as conn:
        user = conn.execute("""
            SELECT id,email,display_name,role,learning_data,password_hash,is_blocked,(profile_photo_type IS NOT NULL) AS has_photo FROM users WHERE email=%s
        """, (email,)).fetchone()
    if len(password) > 128 or not user or user["is_blocked"] or user["role"] != role or not verify_password(password, user["password_hash"]):
        return jsonify(error="Email or password is incorrect."), 401
    return session_response({"user": user_json(user)}, user["id"])


@app.post("/api/logout")
def logout():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    token = request.cookies.get("vinedu_session", "")
    if token:
        with pool.connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=%s", (hashlib.sha256(token.encode()).hexdigest(),))
    response = jsonify(ok=True)
    response.delete_cookie("vinedu_session", path="/", httponly=True, secure=PRODUCTION, samesite="Lax")
    return response


@app.put("/api/data")
def save_data():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in to continue."), 401
    body = api_body()
    allowed = ("progress", "completed", "startedCourses", "bookmarks", "activity", "attempts", "enrolled", "assignments", "meetings", "customCourses", "planner", "notes", "flashcards", "settings")
    data = {key: body[key] for key in allowed if key in body}
    if user["role"] != "admin":
        data.pop("meetings", None)
        data.pop("customCourses", None)
    if len(json.dumps(data)) > 900_000:
        return jsonify(error="Learning data limit exceeded."), 413
    with pool.connection() as conn:
        name = body.get("name")
        if user["role"] == "admin" and isinstance(name, str) and 2 <= len(name.strip()) <= 80:
            updated = "CURRENT_TIMESTAMP" if USE_SQLITE else "NOW()"
            conn.execute(f"UPDATE users SET display_name=%s,updated_at={updated} WHERE id=%s", (name.strip(), user["id"]))
        if data:
            if USE_SQLITE:
                current = conn.execute("SELECT learning_data FROM users WHERE id=%s", (user["id"],)).fetchone()
                stored = json.loads(current["learning_data"] or "{}")
                stored.update(data)
                conn.execute("UPDATE users SET learning_data=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (json.dumps(stored), user["id"]))
            else:
                conn.execute("UPDATE users SET learning_data=learning_data || %s::jsonb,updated_at=NOW() WHERE id=%s", (json.dumps(data), user["id"]))
    return jsonify(ok=True)


@app.get("/api/admin/students")
def students():
    user = current_user()
    if not user:
        return jsonify(error="Please log in to continue."), 401
    if user["role"] != "admin":
        return jsonify(error="Administrator access required."), 403
    with pool.connection() as conn:
        if USE_SQLITE:
            users = conn.execute("SELECT id,email,display_name,created_at,learning_data,is_blocked FROM users WHERE role='student' ORDER BY created_at DESC LIMIT 500").fetchall()
            rows = []
            for student in users:
                learning = json.loads(student["learning_data"] or "{}")
                rows.append({"id": student["id"], "email": student["email"], "display_name": student["display_name"], "created_at": student["created_at"], "enrolled": len(learning.get("enrolled", [])), "quiz_courses": len(learning.get("attempts", {})), "is_blocked": bool(student["is_blocked"])})
        else:
            rows = conn.execute("""
            SELECT id,email,display_name,created_at,is_blocked,
                COALESCE(jsonb_array_length(learning_data->'enrolled'),0) AS enrolled,
                COALESCE((SELECT COUNT(*) FROM jsonb_each(learning_data->'attempts')),0) AS quiz_courses
            FROM users WHERE role='student' ORDER BY created_at DESC LIMIT 500
        """).fetchall()
    return jsonify(students=rows)


@app.get("/api/courses")
def course_changes():
    with pool.connection() as conn:
        rows = conn.execute("SELECT course_id,course_json,is_deleted FROM course_catalog").fetchall()
    overrides, created, deleted = {}, [], []
    for row in rows:
        data = row["course_json"]
        if isinstance(data, str):
            data = json.loads(data or "{}")
        if row["is_deleted"]:
            deleted.append(row["course_id"])
        elif data.get("_custom"):
            created.append({key: value for key, value in data.items() if key != "_custom"})
        else:
            overrides[row["course_id"]] = data
    return jsonify(overrides=overrides, created=created, deleted=deleted)


@app.post("/api/admin/courses")
def admin_save_course():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in as administrator."), 401
    if user["role"] != "admin":
        return jsonify(error="Administrator access required."), 403
    body = api_body()
    course_id = str(body.get("id", "")).strip().lower()
    title = str(body.get("title", "")).strip()
    category = str(body.get("category", "Engineering")).strip()[:60]
    if not re.fullmatch(r"[a-z0-9-]{1,60}", course_id) or not 3 <= len(title) <= 100:
        return jsonify(error="Enter a valid course ID and a title of 3–100 characters."), 400
    topics = body.get("topics", [])
    if not isinstance(topics, list) or not 1 <= len(topics) <= 20 or any(not isinstance(t, str) or len(t) > 120 for t in topics):
        return jsonify(error="Add 1–20 course topics. Each topic may be up to 120 characters."), 400
    existing_quiz = body.get("quiz")
    if not isinstance(existing_quiz, list) or len(existing_quiz) != 5:
        existing_quiz = [["Review the course notes before choosing an answer.", ["Ready to review", "Need another look", "I have a question", "Skip this topic"], 0]] * 5
    course = {"id": course_id, "title": title, "category": category, "icon": str(body.get("icon", "📘"))[:8],
              "level": str(body.get("level", "Beginner"))[:40], "lessons": max(1, min(int(body.get("lessons", len(topics))), 100)),
              "minutes": max(10, min(int(body.get("minutes", 60)), 5000)), "progress": 0,
              "students": 0, "description": str(body.get("description", ""))[:500], "topics": topics,
              "quiz": existing_quiz}
    is_custom = bool(body.get("isCustom", False))
    payload = {**course, "_custom": is_custom}
    now = "CURRENT_TIMESTAMP" if USE_SQLITE else "NOW()"
    with pool.connection() as conn:
        if USE_SQLITE:
            conn.execute("INSERT INTO course_catalog(course_id,course_json,is_deleted) VALUES(%s,%s,0) ON CONFLICT(course_id) DO UPDATE SET course_json=excluded.course_json,is_deleted=0,updated_at=CURRENT_TIMESTAMP", (course_id, json.dumps(payload)))
        else:
            conn.execute(f"INSERT INTO course_catalog(course_id,course_json,is_deleted,updated_at) VALUES(%s,%s::jsonb,FALSE,{now}) ON CONFLICT(course_id) DO UPDATE SET course_json=EXCLUDED.course_json,is_deleted=FALSE,updated_at=NOW()", (course_id, json.dumps(payload)))
    return jsonify(course=course)


@app.delete("/api/admin/courses/<course_id>")
def admin_delete_course(course_id):
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in as administrator."), 401
    if user["role"] != "admin":
        return jsonify(error="Administrator access required."), 403
    if not re.fullmatch(r"[a-z0-9-]{1,60}", course_id):
        return jsonify(error="Invalid course ID."), 400
    now = "CURRENT_TIMESTAMP" if USE_SQLITE else "NOW()"
    with pool.connection() as conn:
        if USE_SQLITE:
            conn.execute("INSERT INTO course_catalog(course_id,course_json,is_deleted) VALUES(%s,'{}',1) ON CONFLICT(course_id) DO UPDATE SET is_deleted=1,updated_at=CURRENT_TIMESTAMP", (course_id,))
        else:
            conn.execute(f"INSERT INTO course_catalog(course_id,course_json,is_deleted,updated_at) VALUES(%s,'{{}}'::jsonb,TRUE,{now}) ON CONFLICT(course_id) DO UPDATE SET is_deleted=TRUE,updated_at=NOW()", (course_id,))
    return jsonify(ok=True)


@app.post("/api/admin/students/<int:student_id>/block")
def admin_block_student(student_id):
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in as administrator."), 401
    if user["role"] != "admin":
        return jsonify(error="Administrator access required."), 403
    blocked = bool(api_body().get("blocked"))
    with pool.connection() as conn:
        result = conn.execute("UPDATE users SET is_blocked=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s AND role='student'", (blocked, student_id))
        if result.rowcount == 0:
            return jsonify(error="Student account not found."), 404
        if blocked:
            conn.execute("DELETE FROM sessions WHERE user_id=%s", (student_id,))
    return jsonify(ok=True, blocked=blocked)


@app.post("/api/admin/password-reset")
def admin_password_reset():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    if rate_limited():
        return jsonify(error="Too many reset attempts. Please wait and try again."), 429
    configured = os.getenv("ADMIN_RESET_TOKEN") if PRODUCTION else os.getenv("DEMO_ADMIN_RESET_TOKEN", "local-demo-reset-code-change-me")
    body = api_body()
    provided = str(body.get("resetToken", ""))
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("newPassword", ""))
    if not configured or not hmac.compare_digest(configured, provided):
        return jsonify(error="Reset code is incorrect. Contact your system administrator."), 401
    if not 12 <= len(password) <= 128:
        return jsonify(error="Use a new password between 12 and 128 characters."), 400
    with pool.connection() as conn:
        admin = conn.execute("SELECT id FROM users WHERE email=%s AND role='admin'", (email,)).fetchone()
        if not admin:
            return jsonify(error="Admin account not found for that email."), 404
        conn.execute("UPDATE users SET password_hash=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (hash_password(password), admin["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=%s", (admin["id"],))
    return jsonify(ok=True)


@app.post("/api/account/password")
def account_password_change():
    if not same_origin():
        return jsonify(error="Request origin rejected."), 403
    user = current_user()
    if not user:
        return jsonify(error="Please log in again."), 401
    body = api_body()
    old_password, new_password = str(body.get("oldPassword", "")), str(body.get("newPassword", ""))
    if not 12 <= len(new_password) <= 128:
        return jsonify(error="Use a new password between 12 and 128 characters."), 400
    with pool.connection() as conn:
        record = conn.execute("SELECT password_hash FROM users WHERE id=%s", (user["id"],)).fetchone()
        if not record or not verify_password(old_password, record["password_hash"]):
            return jsonify(error="Current password is incorrect."), 401
        conn.execute("UPDATE users SET password_hash=%s,updated_at=CURRENT_TIMESTAMP WHERE id=%s", (hash_password(new_password), user["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=%s", (user["id"],))
    response = session_response({"ok": True}, user["id"])
    return response


@app.errorhandler(404)
def not_found(_error):
    if request.path.startswith("/api/"):
        return jsonify(error="API route not found."), 404
    return send_from_directory(PUBLIC, "index.html")


@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


if not USE_SQLITE:
    pool.open(wait=True)
with pool.connection() as _connection:
    schema = """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student','admin')),
            profile_photo BYTEA, profile_photo_type TEXT,
            learning_data JSONB NOT NULL DEFAULT '{"progress":{},"completed":[],"bookmarks":[],"activity":[],"attempts":{},"enrolled":[],"assignments":[],"meetings":[],"customCourses":[],"notes":[],"planner":[],"settings":{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS sessions_expires_at_idx ON sessions(expires_at);
        CREATE INDEX IF NOT EXISTS users_created_at_idx ON users(created_at);
    """
    if USE_SQLITE:
        schema = schema.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
        schema = schema.replace("JSONB NOT NULL", "TEXT NOT NULL")
        schema = schema.replace("::jsonb", "")
        schema = schema.replace("BYTEA", "BLOB")
        schema = schema.replace("TIMESTAMPTZ NOT NULL DEFAULT NOW()", "TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")
        _connection.executescript(schema)
        columns = [row["name"] for row in _connection.execute("PRAGMA table_info(users)").fetchall()]
        if "is_blocked" not in columns:
            _connection.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT FALSE")
        if "profile_photo" not in columns:
            _connection.execute("ALTER TABLE users ADD COLUMN profile_photo BLOB")
        if "profile_photo_type" not in columns:
            _connection.execute("ALTER TABLE users ADD COLUMN profile_photo_type TEXT")
    else:
        _connection.execute(schema)
        _connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN NOT NULL DEFAULT FALSE")
        _connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo BYTEA")
        _connection.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_photo_type TEXT")
        _connection.execute("CREATE TABLE IF NOT EXISTS course_catalog(course_id TEXT PRIMARY KEY,course_json JSONB NOT NULL DEFAULT '{}'::jsonb,is_deleted BOOLEAN NOT NULL DEFAULT FALSE,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
    if USE_SQLITE:
        _connection.execute("CREATE TABLE IF NOT EXISTS course_catalog(course_id TEXT PRIMARY KEY,course_json TEXT NOT NULL DEFAULT '{}',is_deleted INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    _connection.execute("DELETE FROM sessions WHERE expires_at<" + ("CURRENT_TIMESTAMP" if USE_SQLITE else "NOW()"))
provision_admin()

if __name__ == "__main__":
    app.run(host="127.0.0.1" if LOCAL_DEMO else "0.0.0.0", port=int(os.getenv("PORT", "3000")), debug=False)
