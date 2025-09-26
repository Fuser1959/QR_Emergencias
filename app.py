import os
import re
from datetime import timedelta

from flask import (
    Flask, request, render_template, redirect, url_for,
    session, abort, jsonify
)
import mysql.connector
from werkzeug.security import check_password_hash

# -----------------------------
# Configuración de la app Flask
# -----------------------------
app = Flask(__name__)

# SECRET KEY (usá una variable de entorno en producción)
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

# ------------------------------------------------
# Helpers de DB y de sesión
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

def get_current_user():
    uid = session.get("uid")
    if not uid:
        return None
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, email, nombre, apellido FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

def _is_safe_next(nxt: str) -> bool:
    # Permitimos solo paths locales (empiezan con /) para evitar open redirect
    return isinstance(nxt, str) and nxt.startswith("/")

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
    # Por ahora, el "inicio" es el login
    return redirect(url_for("login"))

# ------------------------------------------------
# Autenticación
# ------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    nxt = request.args.get("next", "/panel")
    if request.method == "POST":
        # preservamos next también desde POST si vino
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
            if not user["password_hash"]:
                error = "Usuario sin contraseña configurada"
            elif not check_password_hash(user["password_hash"], password):
                error = "Contraseña inválida"
            else:
                # ok
                session.permanent = True
                session["uid"] = user["id"]
                # Validamos next
                return redirect(nxt if _is_safe_next(nxt) else url_for("panel"))

    # GET o error → mostramos template
    return render_template("login.html", error=error, next=nxt)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ------------------------------------------------
# Panel del usuario logueado
# ------------------------------------------------
@app.route("/panel")
def panel():
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next="/panel"))

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, public_code, user_id, claimed_at
        FROM qr_codes
        WHERE user_id=%s
        ORDER BY id DESC
    """, (user["id"],))
    qrs = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("panel.html", user=user, qrs=qrs)

# ------------------------------------------------
# Flujo público QR (virgen → login+claim, reclamado → ficha)
# ------------------------------------------------
@app.route("/v/<code>")
def view_public_code(code):
    """
    Entrada pública de una etiqueta con public_code.
    - Si no existe -> 404
    - Si existe y no está reclamada (user_id IS NULL) -> redirige a /login?next=/claim/<code>
    - Si ya está reclamada -> redirige a /emergencia/<id>
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
    Reclama (asocia) el public_code al usuario logueado.
    Si no está logueado → /login?next=/claim/<code>
    Si el código no existe → 404
    Si ya está reclamado → redirige a /emergencia/<id>
    """
    user = get_current_user()
    if not user:
        return redirect(url_for("login", next=f"/claim/{code}"))

    conn = get_db()
    cur = conn.cursor(dictionary=True)

    # Buscamos el QR
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s", (code,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        abort(404)

    # Si ya estaba reclamado, vamos a la ficha
    if row["user_id"] is not None:
        qr_id = row["id"]
        cur.close()
        conn.close()
        return redirect(url_for("emergencia", qr_id=qr_id))

    # Reclamar (solo si sigue virgen)
    cur.execute(
        "UPDATE qr_codes SET user_id=%s, claimed_at=NOW() WHERE public_code=%s AND user_id IS NULL",
        (user["id"], code)
    )
    # Recuperamos ID para mostrarlo si queremos
    cur.execute("SELECT id FROM qr_codes WHERE public_code=%s", (code,))
    row2 = cur.fetchone()
    cur.close()
    conn.close()

    # A panel (ahí verá el nuevo QR)
    return redirect(url_for("panel"))

# ------------------------------------------------
# Ficha pública (solo si el QR tiene dueño)
# ------------------------------------------------
@app.route("/emergencia/<int:qr_id>")
def emergencia(qr_id):
    """
    Muestra la ficha SOLO si el QR ya fue reclamado (user_id NO NULL).
    Si no tiene dueño -> 404
    """
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT q.id, q.user_id,
               u.nombre, u.apellido, u.grupo_sanguineo, u.alergias,
               u.contacto1, u.contacto2
        FROM qr_codes q
        LEFT JOIN users u ON u.id = q.user_id
        WHERE q.id=%s
    """, (qr_id,))
    data = cur.fetchone()
    cur.close()
    conn.close()

    if not data:
        abort(404)

    if data["user_id"] is None:
        # Si preferís forzar flujo de claim, se podría redirigir:
        # return redirect(url_for("login", next=f"/claim/{public_code}"))
        abort(404)

    # Render (adaptá a tu template 'emergencia.html')
    return render_template(
        "emergencia.html",
        nombre=(data.get("nombre") or ""),
        apellido=(data.get("apellido") or ""),
        grupo_sanguineo=(data.get("grupo_sanguineo") or ""),
        alergias=(data.get("alergias") or "No"),
        contacto1=(data.get("contacto1") or ""),
        contacto2=(data.get("contacto2") or "")
    )

# ------------------------------------------------
# Filtro de path (por si querés exponer menos info en logs)
# ------------------------------------------------
@app.after_request
def add_headers(resp):
    # cache bust
    resp.headers["Cache-Control"] = "no-store"
    return resp


if __name__ == "__main__":
    # Útil para correr local
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
