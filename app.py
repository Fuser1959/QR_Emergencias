import os
from datetime import timedelta

from flask import (
    Flask, request, render_template, redirect, url_for,
    session, abort, jsonify, g
)
import mysql.connector
from werkzeug.security import check_password_hash

# -----------------------------
# Configuración de la app Flask
# -----------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "change-me-in-prod")
app.permanent_session_lifetime = timedelta(days=14)

# -----------------------------
# Config DB (toma primero QR_DB_*, si no, MYSQL*)
# -----------------------------
def _env(*names, default=None):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return default

DB_HOST = _env("QR_DB_HOST", "MYSQLHOST", default="mysql.railway.internal")
DB_PORT = int(_env("QR_DB_PORT", "MYSQLPORT", default="3306"))
DB_NAME = _env("QR_DB_NAME", "MYSQLDATABASE", default="railway")
DB_USER = _env("QR_DB_USER", "MYSQLUSER", default="root")
DB_PASS = _env("QR_DB_PASSWORD", "MYSQLPASSWORD", default="")

def get_db():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        autocommit=True
    )

# -----------------------------
# Sesión / usuario actual
# -----------------------------
def get_current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    # Traemos TODO lo que exista en users (no forzamos nombres de columnas)
    cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

@app.before_request
def _load_g_user():
    g.user = get_current_user()

def _is_safe_next(nxt: str) -> bool:
    return isinstance(nxt, str) and nxt.startswith("/")

# -----------------------------
# Rutas utilitarias
# -----------------------------
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

# -----------------------------
# Autenticación
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    nxt = request.args.get("next", "/panel")
    if request.method == "POST":
        nxt = request.form.get("next", nxt) or "/panel"
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, email, password_hash FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user:
            error = "Usuario inexistente"
        else:
            if not user.get("password_hash"):
                error = "Usuario sin contraseña configurada"
            elif not check_password_hash(user["password_hash"], password):
                error = "Contraseña inválida"
            else:
                session.permanent = True
                session["uid"] = user["id"]
                return redirect(nxt if _is_safe_next(nxt) else url_for("panel"))

    return render_template("login.html", error=error, next=nxt)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------
# Panel
# -----------------------------
@app.route("/panel")
def panel():
    if not g.user:
        return redirect(url_for("login", next="/panel"))

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, public_code, user_id, claimed_at, qr_code_string
        FROM qr_codes
        WHERE user_id=%s
        ORDER BY id DESC
    """, (g.user["id"],))
    codes = cur.fetchall()
    cur.close()
    conn.close()

    # Tu template usa g.user y 'codes'
    return render_template("panel.html", codes=codes)

# -----------------------------
# Flujo público QR
# -----------------------------
@app.route("/v/<code>")
def view_by_code(code):
    """
    Entrada pública:
      - si no existe -> 404
      - si existe y user_id IS NULL -> /login?next=/claim/<code>
      - si existe y user_id NO NULL -> /emergencia/<id>
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        abort(404)

    if row["user_id"] is None:
        return redirect(url_for("login", next=f"/claim/{code}"))

    return redirect(url_for("emergencia", qr_id=row["id"]))

@app.route("/claim/<code>", methods=["GET"])
def claim_code(code):
    """
    Reclama el código para el usuario logueado.
    """
    if not g.user:
        return redirect(url_for("login", next=f"/claim/{code}"))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)

    if row["user_id"] is not None:
        cur.close()
        conn.close()
        return redirect(url_for("emergencia", qr_id=row["id"]))

    # Reclamar solo si sigue virgen
    cur.execute(
        "UPDATE qr_codes SET user_id=%s, claimed_at=NOW() WHERE public_code=%s AND user_id IS NULL",
        (g.user["id"], code)
    )
    cur.close()
    conn.close()

    return redirect(url_for("panel"))

# -----------------------------
# Ficha pública (solo QR con dueño)
# -----------------------------
@app.route("/emergencia/<int:qr_id>")
def emergencia(qr_id):
    """
    Muestra la ficha SOLO si q.user_id NO NULL.
    No referenciamos columnas inexistentes: primero leemos el QR,
    luego hacemos SELECT * del usuario y mapeamos con defaults.
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("SELECT id, user_id FROM qr_codes WHERE id=%s", (qr_id,))
    q = cur.fetchone()
    if not q:
        cur.close()
        conn.close()
        abort(404)

    if q["user_id"] is None:
        cur.close()
        conn.close()
        abort(404)

    # Traemos TODO del usuario, sin nombrar columnas
    cur.execute("SELECT * FROM users WHERE id=%s", (q["user_id"],))
    u = cur.fetchone()
    cur.close()
    conn.close()

    if not u:
        abort(404)

    # Mapeo a las keys que usa tu template 'emergencia.html'
    data = {
        # Si no hay nombre, mostramos el email como identificador
        "nombre": (u.get("nombre") or u.get("full_name") or u.get("email") or "").strip(),
        "apellido": (u.get("apellido") or "").strip(),
        "factor_sanguineo": (u.get("factor_sanguineo") or u.get("grupo_sanguineo") or "").strip(),
        # Interpretamos flags/strings variados como boolean para 'tiene_alergias'
        "tiene_alergias": bool(u.get("tiene_alergias") or u.get("alergias") in ("si", "sí", "1", 1, True)),
        "telefono_1": (u.get("telefono_1") or u.get("contacto1") or "").strip(),
        "telefono_2": (u.get("telefono_2") or u.get("contacto2") or "").strip(),
        "instructivo_url": (u.get("instructivo_url") or "").strip(),
    }

    return render_template("emergencia.html", data=data)

# -----------------------------
# No-cache
# -----------------------------
@app.after_request
def add_headers(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
