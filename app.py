import os
import re
import secrets
import hmac
from datetime import timedelta, datetime

from flask import (
    Flask, request, render_template, redirect, url_for,
    session, abort, jsonify, flash, g
)
import mysql.connector
from werkzeug.security import check_password_hash, generate_password_hash

# --- Cargar variables desde .env cuando corremos local ---
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# -----------------------------
# Configuración de la app Flask
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-prod")
app.permanent_session_lifetime = timedelta(days=14)

# -----------------------------
# Config DB
# -----------------------------
def _env(*names, default=None):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default

DB_HOST = _env("QR_DB_HOST", "MYSQLHOST", default="127.0.0.1")
DB_PORT = int(_env("QR_DB_PORT", "MYSQLPORT", default="3306"))
DB_NAME = _env("QR_DB_NAME", "MYSQLDATABASE", default="railway")
DB_USER = _env("QR_DB_USER", "MYSQLUSER", default="root")
DB_PASS = _env("QR_DB_PASSWORD", "MYSQLPASSWORD", default="")

# Config email (para reset de contraseña)
MAIL_SERVER   = os.environ.get("MAIL_SERVER", "")
MAIL_PORT     = int(os.environ.get("MAIL_PORT", "587"))
MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "")
MAIL_FROM     = os.environ.get("MAIL_FROM", MAIL_USERNAME)
APP_BASE_URL  = os.environ.get("APP_BASE_URL", "http://localhost:5000")

# ------------------------------------------------
# Helpers de DB
# ------------------------------------------------
def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=True
    )

# Mapeo de nombres de columnas (cacheado en memoria)
_USER_COLMAP = None

def _detect_user_columns():
    """
    Detecta nombres reales de columnas en 'users' para compatibilidad
    con distintas versiones del schema.
    """
    global _USER_COLMAP
    if _USER_COLMAP is not None:
        return _USER_COLMAP

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM users")
        rows = cur.fetchall()
        cols = {r[0] for r in rows}
    finally:
        cur.close()
        conn.close()

    def pick(*candidates):
        for c in candidates:
            if c in cols:
                return c
        return None

    _USER_COLMAP = {
        "first":     pick("nombre", "name", "first_name"),
        "last":      pick("apellido", "surname", "last_name"),
        "blood":     pick("grupo_sanguineo", "blood_type"),
        "allergies": pick("alergias", "allergies", "allergies_bool"),
        "phone1":    pick("contacto1", "contact_phone_1", "phone1"),
        "phone2":    pick("contacto2", "contact_phone_2", "phone2"),
        "email":     pick("email"),
        "pwd":       pick("password_hash", "pass_hash"),
        "id":        pick("id"),
        "reset_token":   pick("reset_token"),
        "reset_expires": pick("reset_expires"),
    }
    return _USER_COLMAP


def _invalidate_colmap():
    """Fuerza re-detección de columnas (usar tras migraciones)."""
    global _USER_COLMAP
    _USER_COLMAP = None


def get_current_user():
    uid = session.get("uid")
    if not uid:
        return None

    m = _detect_user_columns()
    id_col    = m["id"] or "id"
    email_col = m["email"] or "email"
    first_col = m["first"]
    last_col  = m["last"]

    select_parts = [f"{id_col} AS id", f"{email_col} AS email"]
    select_parts.append(f"{first_col} AS nombre"   if first_col else "'' AS nombre")
    select_parts.append(f"{last_col}  AS apellido" if last_col  else "'' AS apellido")

    sql = f"SELECT {', '.join(select_parts)} FROM users WHERE {id_col}=%s"

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user


def _is_safe_next(nxt: str) -> bool:
    return isinstance(nxt, str) and nxt.startswith("/")


def _ensure_profile_columns():
    """
    Agrega columnas de perfil médico a 'users' si no existen.
    Se llama una vez al arrancar la app.
    """
    needed = [
        ("nombre",          "VARCHAR(100) NULL"),
        ("apellido",        "VARCHAR(100) NULL"),
        ("grupo_sanguineo", "VARCHAR(10)  NULL"),
        ("alergias",        "VARCHAR(255) NULL"),
        ("contacto1",       "VARCHAR(40)  NULL"),
        ("contacto2",       "VARCHAR(40)  NULL"),
        ("reset_token",     "VARCHAR(64)  NULL"),
        ("reset_expires",   "DATETIME     NULL"),
    ]
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM users")
        existing = {r[0] for r in cur.fetchall()}
        for col, ddl in needed:
            if col not in existing:
                cur.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        # Índice para reset_token
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='users' AND INDEX_NAME='idx_reset_token'
        """)
        if cur.fetchone()[0] == 0:
            cur.execute("CREATE INDEX idx_reset_token ON users(reset_token)")
        cur.close()
        conn.close()
        _invalidate_colmap()
    except Exception as e:
        print(f"[WARN] _ensure_profile_columns: {e}")


# Ejecutar al arrancar
with app.app_context():
    _ensure_profile_columns()


# ------------------------------------------------
# Rate limiting simple (en memoria, por IP)
# ------------------------------------------------
import threading
from collections import defaultdict

_rl_lock   = threading.Lock()
_rl_counts = defaultdict(list)   # ip -> [timestamp, ...]

RATE_LIMIT_WINDOW  = 60   # segundos
RATE_LIMIT_MAX     = 10   # intentos por ventana


def _rate_limited(ip: str) -> bool:
    """Devuelve True si la IP superó el límite."""
    now = datetime.utcnow().timestamp()
    with _rl_lock:
        hits = [t for t in _rl_counts[ip] if now - t < RATE_LIMIT_WINDOW]
        hits.append(now)
        _rl_counts[ip] = hits
        return len(hits) > RATE_LIMIT_MAX


# ------------------------------------------------
# CSRF protection (token por sesión)
# ------------------------------------------------
def _csrf_token() -> str:
    """Genera o recupera el token CSRF de la sesión."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return session["csrf_token"]


def _csrf_valid() -> bool:
    """Valida el token CSRF en POST requests."""
    token = session.get("csrf_token")
    form_token = request.form.get("csrf_token", "")
    if not token or not form_token:
        return False
    return hmac.compare_digest(token, form_token)


# Inyectar csrf_token en todos los templates
@app.context_processor
def inject_csrf():
    return {"csrf_token": _csrf_token()}


# Validar CSRF en todos los POST (excepto rutas de API/health)
_CSRF_EXEMPT = {"/health", "/db_ping", "/__ping__"}

@app.before_request
def check_csrf():
    if request.method == "POST" and request.path not in _CSRF_EXEMPT:
        if not _csrf_valid():
            abort(403)


# ------------------------------------------------
# Email helper
# ------------------------------------------------
def _send_reset_email(to_email: str, reset_url: str) -> bool:
    """
    Envía el email de reset. Requiere MAIL_SERVER, MAIL_USERNAME, MAIL_PASSWORD.
    Devuelve True si se envió, False si no hay config de email.
    """
    if not MAIL_SERVER or not MAIL_USERNAME:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Recuperar contraseña — QR Emergencia"
        msg["From"]    = MAIL_FROM
        msg["To"]      = to_email

        text_body = f"""Hola,

Recibimos una solicitud para restablecer tu contraseña.
Hacé clic en el siguiente enlace (válido por 1 hora):

{reset_url}

Si no solicitaste esto, ignorá este mensaje.
"""
        html_body = f"""<p>Hola,</p>
<p>Recibimos una solicitud para restablecer tu contraseña.</p>
<p><a href="{reset_url}" style="background:#2563eb;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none;display:inline-block;">
  Restablecer contraseña
</a></p>
<p style="color:#888;font-size:13px;">El enlace es válido por 1 hora. Si no solicitaste esto, ignorá este mensaje.</p>
"""
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
            smtp.sendmail(MAIL_FROM, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[ERROR] send_reset_email: {e}")
        return False


# ------------------------------------------------
# Rutas utilitarias
# ------------------------------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/db_ping")
def db_ping():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"status": "db_ok", "db_host": DB_HOST, "db_name": DB_NAME})
    except Exception as e:
        return jsonify({"status": "db_error", "db_host": DB_HOST, "db_name": DB_NAME, "error": str(e)}), 500


@app.route("/")
def home():
    return redirect(url_for("login"))


# ------------------------------------------------
# Autenticación
# ------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    nxt = request.args.get("next", "/panel")
    if request.method == "POST":
        nxt = request.form.get("next", nxt) or "/panel"

        ip = request.remote_addr or "unknown"
        if _rate_limited(ip):
            error = "Demasiados intentos. Esperá un minuto e intentá de nuevo."
            return render_template("login.html", error=error, next=nxt)

        email    = (request.form.get("email")    or "").strip().lower()
        password =  request.form.get("password") or ""

        m         = _detect_user_columns()
        email_col = m["email"] or "email"
        pwd_col   = m["pwd"]   or "password_hash"

        conn = get_db()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT {m['id']} AS id, {email_col} AS email, {pwd_col} AS password_hash "
            f"FROM users WHERE {email_col}=%s", (email,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            error = "Email o contraseña incorrectos."
        elif not user["password_hash"]:
            error = "Usuario sin contraseña configurada."
        elif not check_password_hash(user["password_hash"], password):
            error = "Email o contraseña incorrectos."
        else:
            session.permanent = True
            session["uid"] = user["id"]
            return redirect(nxt if _is_safe_next(nxt) else url_for("panel"))

    return render_template("login.html", error=error, next=nxt)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# -------- /register --------
@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    nxt = request.args.get("next", "/panel")
    if request.method == "POST":
        nxt      = request.form.get("next", nxt) or "/panel"

        ip = request.remote_addr or "unknown"
        if _rate_limited(ip):
            error = "Demasiados intentos. Esperá un minuto e intentá de nuevo."
            return render_template("register.html", error=error, next=nxt)

        nombre   = (request.form.get("nombre")   or "").strip()
        apellido = (request.form.get("apellido") or "").strip()
        email    = (request.form.get("email")    or "").strip().lower()
        password =  request.form.get("password") or ""

        if not (email and password):
            error = "Completá email y contraseña."
        elif len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        else:
            m         = _detect_user_columns()
            email_col = m["email"] or "email"
            pwd_col   = m["pwd"]   or "password_hash"
            first_col = m["first"]
            last_col  = m["last"]

            conn = get_db()
            cur  = conn.cursor(dictionary=True)
            cur.execute(f"SELECT {m['id']} AS id FROM users WHERE {email_col}=%s", (email,))
            exists = cur.fetchone()
            if exists:
                error = "Ese email ya está registrado."
                cur.close(); conn.close()
            else:
                pwd_hash = generate_password_hash(password)
                cur.execute(
                    f"INSERT INTO users ({email_col}, {pwd_col}) VALUES (%s, %s)",
                    (email, pwd_hash)
                )
                uid = cur.lastrowid

                update_parts, params = [], []
                if first_col and nombre:
                    update_parts.append(f"{first_col}=%s"); params.append(nombre)
                if last_col and apellido:
                    update_parts.append(f"{last_col}=%s"); params.append(apellido)
                if update_parts:
                    params.append(uid)
                    cur.execute(
                        f"UPDATE users SET {', '.join(update_parts)} WHERE {m['id']}=%s",
                        tuple(params)
                    )

                cur.close(); conn.close()

                session.permanent = True
                session["uid"] = uid

                # Si viene de un claim, completar el claim y luego ir al perfil
                if nxt.startswith("/claim/"):
                    return redirect(nxt)
                # Si no tiene datos médicos, llevar al perfil para completarlos
                return redirect(url_for("perfil", onboarding=1))

    return render_template("register.html", error=error, next=nxt)


# -------- /forgot --------
@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    sent  = False
    email = ""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        if email:
            m         = _detect_user_columns()
            id_col    = m["id"]    or "id"
            email_col = m["email"] or "email"
            rt_col    = m["reset_token"]
            re_col    = m["reset_expires"]

            conn = get_db()
            cur  = conn.cursor(dictionary=True)
            cur.execute(f"SELECT {id_col} AS id FROM users WHERE {email_col}=%s", (email,))
            user = cur.fetchone()

            if user and rt_col and re_col:
                token   = secrets.token_urlsafe(32)
                expires = datetime.utcnow() + timedelta(hours=1)
                cur.execute(
                    f"UPDATE users SET {rt_col}=%s, {re_col}=%s WHERE {id_col}=%s",
                    (token, expires, user["id"])
                )
                reset_url = f"{APP_BASE_URL}/reset/{token}"
                sent_ok   = _send_reset_email(email, reset_url)
                if not sent_ok:
                    # Sin config de email: mostrar el link en consola (útil en dev)
                    print(f"[DEV] Reset URL para {email}: {reset_url}")

            cur.close(); conn.close()
        sent = True  # Siempre mostrar "te enviamos instrucciones" (no revelar si existe)

    return render_template("forgot.html", sent=sent, email=email)


# -------- /reset/<token> --------
@app.route("/reset/<token>", methods=["GET", "POST"])
def reset_password(token):
    m      = _detect_user_columns()
    id_col = m["id"]    or "id"
    rt_col = m["reset_token"]
    re_col = m["reset_expires"]
    pw_col = m["pwd"]   or "password_hash"

    if not rt_col or not re_col:
        # Columnas no existen aún — mostrar error genérico
        return render_template("reset_password.html", invalid=True)

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute(
        f"SELECT {id_col} AS id, {re_col} AS expires FROM users WHERE {rt_col}=%s",
        (token,)
    )
    user = cur.fetchone()

    if not user or not user["expires"] or datetime.utcnow() > user["expires"]:
        cur.close(); conn.close()
        return render_template("reset_password.html", invalid=True)

    error = None
    if request.method == "POST":
        password  = request.form.get("password")  or ""
        password2 = request.form.get("password2") or ""
        if len(password) < 6:
            error = "La contraseña debe tener al menos 6 caracteres."
        elif password != password2:
            error = "Las contraseñas no coinciden."
        else:
            pwd_hash = generate_password_hash(password)
            cur.execute(
                f"UPDATE users SET {pw_col}=%s, {rt_col}=NULL, {re_col}=NULL WHERE {id_col}=%s",
                (pwd_hash, user["id"])
            )
            cur.close(); conn.close()
            flash("Contraseña actualizada. Ya podés iniciar sesión.", "success")
            return redirect(url_for("login"))

    cur.close(); conn.close()
    return render_template("reset_password.html", invalid=False, error=error)


# ------------------------------------------------
# Perfil médico
# ------------------------------------------------
@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next="/perfil"))

    onboarding = request.args.get("onboarding", "0") == "1"
    m          = _detect_user_columns()
    id_col     = m["id"] or "id"

    # Columnas disponibles para el perfil
    field_map = {
        "nombre":          m["first"],
        "apellido":        m["last"],
        "grupo_sanguineo": m["blood"],
        "alergias":        m["allergies"],
        "contacto1":       m["phone1"],
        "contacto2":       m["phone2"],
    }
    available = {k: v for k, v in field_map.items() if v}

    error   = None
    success = False

    if request.method == "POST":
        updates, params = [], []
        for field, col in available.items():
            val = (request.form.get(field) or "").strip()
            updates.append(f"{col}=%s")
            params.append(val)

        if updates:
            params.append(user["id"])
            conn = get_db()
            cur  = conn.cursor()
            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE {id_col}=%s",
                tuple(params)
            )
            cur.close(); conn.close()

        success = True
        if onboarding:
            return redirect(url_for("panel"))

    # Cargar datos actuales
    if available:
        select_parts = [f"{col} AS {field}" for field, col in available.items()]
        conn = get_db()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT {', '.join(select_parts)} FROM users WHERE {id_col}=%s",
            (user["id"],)
        )
        profile = cur.fetchone() or {}
        cur.close(); conn.close()
    else:
        profile = {}

    return render_template(
        "perfil.html",
        user=user,
        profile=profile,
        onboarding=onboarding,
        success=success,
        error=error,
    )


# ------------------------------------------------
# Panel
# ------------------------------------------------
@app.route("/panel")
def panel():
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next="/panel"))

    m      = _detect_user_columns()
    id_col = m["id"] or "id"

    # Verificar si tiene datos médicos cargados
    profile_complete = False
    if m["first"] or m["blood"] or m["phone1"]:
        check_cols = [c for c in [m["first"], m["blood"], m["phone1"]] if c]
        conn = get_db()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT {', '.join(check_cols)} FROM users WHERE {id_col}=%s",
            (user["id"],)
        )
        row = cur.fetchone() or {}
        cur.close(); conn.close()
        profile_complete = any(row.get(c) for c in check_cols)

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, public_code, user_id, claimed_at
        FROM qr_codes
        WHERE user_id=%s
        ORDER BY id DESC
    """, (user["id"],))
    qrs = cur.fetchall()
    cur.close(); conn.close()

    return render_template(
        "panel.html",
        user=user,
        qrs=qrs,
        profile_complete=profile_complete,
    )


# ------------------------------------------------
# Flujo público QR
# ------------------------------------------------
@app.route("/v/<code>")
def view_public_code(code):
    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        abort(404)

    if row["user_id"] is None:
        # QR sin dueño: llevar a login/register para reclamarlo
        user = get_current_user()
        if user:
            return redirect(url_for("claim_code", code=code))
        return redirect(url_for("login", next=f"/claim/{code}"))

    return redirect(url_for("emergencia", qr_id=row["id"]))


# --- Carga manual del código ---
@app.route("/claim", methods=["GET", "POST"])
def claim_manual():
    error = None
    if request.method == "POST":
        code = (request.form.get("code") or "").strip().upper()
        if not code:
            error = "Ingresá el código."
        elif not re.fullmatch(r"[A-Z0-9\-]{4,64}", code):
            error = "Formato de código inválido."
        else:
            conn = get_db()
            cur  = conn.cursor(dictionary=True)
            cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
            row = cur.fetchone()
            cur.close(); conn.close()

            if not row:
                error = "El código no existe."
            else:
                user = get_current_user()
                if row["user_id"] is None:
                    if not user:
                        return redirect(url_for("login", next=f"/claim/{code}"))
                    return redirect(url_for("claim_code", code=code))
                elif user and row["user_id"] == user["id"]:
                    return redirect(url_for("panel"))
                else:
                    # Ya tiene dueño
                    error = "Este código ya está asociado a otra cuenta."

    return render_template("claim_manual.html", error=error)


@app.route("/claim/<code>", methods=["GET"])
def claim_code(code):
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next=f"/claim/{code}"))

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        abort(404)

    if row["user_id"] is not None:
        if row["user_id"] == user["id"]:
            cur.close(); conn.close()
            return redirect(url_for("panel"))
        # Ya tiene otro dueño → mostrar ficha pública
        qr_id = row["id"]
        cur.close(); conn.close()
        return redirect(url_for("emergencia", qr_id=qr_id))

    cur.execute(
        "UPDATE qr_codes SET user_id=%s, claimed_at=NOW() WHERE public_code=%s AND user_id IS NULL",
        (user["id"], code)
    )
    cur.close(); conn.close()

    # Verificar si tiene perfil completo; si no, llevar al onboarding
    m      = _detect_user_columns()
    id_col = m["id"] or "id"
    check_cols = [c for c in [m["first"], m["blood"], m["phone1"]] if c]
    if check_cols:
        conn = get_db()
        cur  = conn.cursor(dictionary=True)
        cur.execute(
            f"SELECT {', '.join(check_cols)} FROM users WHERE {id_col}=%s",
            (user["id"],)
        )
        row2 = cur.fetchone() or {}
        cur.close(); conn.close()
        if not any(row2.get(c) for c in check_cols):
            return redirect(url_for("perfil", onboarding=1))

    return redirect(url_for("panel"))


# ------------------------------------------------
# Ficha pública de emergencia
# ------------------------------------------------
@app.route("/emergencia/<int:qr_id>")
def emergencia(qr_id):
    m = _detect_user_columns()
    first_col     = m["first"]
    last_col      = m["last"]
    blood_col     = m["blood"]
    allergies_col = m["allergies"]
    phone1_col    = m["phone1"]
    phone2_col    = m["phone2"]
    id_col        = m["id"] or "id"

    parts = []
    parts.append(f"u.{first_col} AS nombre"         if first_col     else "'' AS nombre")
    parts.append(f"u.{last_col}  AS apellido"        if last_col      else "'' AS apellido")
    parts.append(f"u.{blood_col} AS grupo_sanguineo" if blood_col     else "'' AS grupo_sanguineo")
    parts.append(f"u.{allergies_col} AS alergias"    if allergies_col else "'' AS alergias")
    parts.append(f"u.{phone1_col} AS contacto1"      if phone1_col    else "'' AS contacto1")
    parts.append(f"u.{phone2_col} AS contacto2"      if phone2_col    else "'' AS contacto2")

    sql = f"""
        SELECT q.id, q.user_id, {', '.join(parts)}
        FROM qr_codes q
        LEFT JOIN users u ON u.{id_col} = q.user_id
        WHERE q.id=%s
    """

    conn = get_db()
    cur  = conn.cursor(dictionary=True)
    cur.execute(sql, (qr_id,))
    data = cur.fetchone()
    cur.close(); conn.close()

    if not data or data["user_id"] is None:
        abort(404)

    return render_template(
        "emergencia.html",
        nombre         = (data.get("nombre")         or ""),
        apellido       = (data.get("apellido")        or ""),
        grupo_sanguineo= (data.get("grupo_sanguineo") or ""),
        alergias       = (data.get("alergias")        or ""),
        contacto1      = (data.get("contacto1")       or ""),
        contacto2      = (data.get("contacto2")       or ""),
    )


# ------------------------------------------------
# No cachear respuestas
# ------------------------------------------------
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---- Auxiliares ----
print("[DEBUG] app.py cargado OK")


@app.route("/__ping__", methods=["GET"])
def __ping__():
    return "pong", 200


# ------------------------------------------------
# Entrypoint
# ------------------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
