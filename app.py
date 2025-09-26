import os
import re
import datetime
from urllib.parse import urlparse

from flask import (
    Flask, request, jsonify, render_template, redirect, url_for,
    session, g, abort, make_response
)
import mysql.connector

# -----------------------------
# Config
# -----------------------------
app = Flask(__name__)

# Clave de sesión
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

DB_HOST = os.environ.get("QR_DB_HOST", os.environ.get("MYSQLHOST", "mysql.railway.internal"))
DB_NAME = os.environ.get("QR_DB_NAME", os.environ.get("MYSQLDATABASE", "railway"))
DB_USER = os.environ.get("QR_DB_USER", os.environ.get("MYSQLUSER", "root"))
DB_PASS = os.environ.get("QR_DB_PASSWORD", os.environ.get("MYSQLPASSWORD", ""))
DB_PORT = int(os.environ.get("MYSQLPORT", "3306"))

# -----------------------------
# Helpers DB
# -----------------------------
def get_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, database=DB_NAME
        , autocommit=True
    )

def safe_next(url_value: str) -> str | None:
    """Solo permite rutas relativas tipo '/claim/XYZ'."""
    if not url_value:
        return None
    parsed = urlparse(url_value)
    # solo path relativo, sin esquema ni host
    if parsed.scheme or parsed.netloc:
        return None
    # evitar cosas raras
    if not url_value.startswith("/"):
        return None
    return url_value

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("""
            SELECT id, email, COALESCE(CONCAT_WS(' ', nombre, apellido), email) AS full_name
            FROM users WHERE id=%s
        """, (uid,))
        row = cur.fetchone()
        cur.close(); cnx.close()
        return row
    except Exception:
        return None

@app.before_request
def load_user():
    g.user = get_current_user()

# -----------------------------
# Rutas básicas
# -----------------------------
@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/db_ping")
def db_ping():
    try:
        cnx = get_db(); cur = cnx.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close(); cnx.close()
        return jsonify({"status": "db_ok", "db_host": DB_HOST, "db_name": DB_NAME})
    except Exception as e:
        return jsonify({"status": "db_error", "error": str(e)}), 500

# -----------------------------
# Vistas públicas de emergencia
# -----------------------------
@app.route("/emergencia/<int:qr_id>")
def emergencia(qr_id):
    """Muestra la ficha pública del QR por id."""
    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("""
            SELECT q.id, q.user_id, u.nombre, u.apellido, u.blood_type, u.has_allergies,
                   u.contact1_label, u.contact1_phone, u.contact2_label, u.contact2_phone
            FROM qr_codes q
            LEFT JOIN users u ON u.id = q.user_id
            WHERE q.id=%s
        """, (qr_id,))
        row = cur.fetchone()
        cur.close(); cnx.close()
        if not row or not row["user_id"]:
            return "QR no encontrado o sin datos.", 404

        # Render simple con plantilla mínima (ya la tenías como templates/emergencia.html)
        return render_template("emergencia.html", d=row)
    except Exception as e:
        return f"Error de base de datos: {e}", 500

# -----------------------------
# Flujo de etiquetas (v/code)
# -----------------------------
@app.route("/v/<public_code>")
def view_by_public_code(public_code):
    """Entrada del QR físico. Decide si redirige a claim o a la ficha."""
    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("""
            SELECT id, user_id FROM qr_codes WHERE public_code=%s
        """, (public_code,))
        row = cur.fetchone()
        cur.close(); cnx.close()

        if not row:
            return "Etiqueta inexistente.", 404

        if row["user_id"] is None:
            # Etiqueta virgen: pedimos login y mandamos a claim
            next_url = f"/claim/{public_code}"
            return redirect(url_for("login", next=next_url))
        else:
            # Ya reclamada → ficha pública
            return redirect(url_for("emergencia", qr_id=row["id"]))
    except Exception as e:
        return f"Error: {e}", 500

# -----------------------------
# Login / Logout
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        # no tocar DB en GET; solo mostrar formulario
        next_param = safe_next(request.args.get("next", ""))
        return render_template("login.html", next=next_param or "")

    # POST
    email = (request.form.get("email") or "").strip().lower()
    password = request.form.get("password") or ""
    next_param = safe_next(request.form.get("next", ""))

    if not email or not password:
        return render_template("login.html", next=next_param or "", error="Completa email y contraseña")

    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT id, email, password_hash FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close(); cnx.close()
    except Exception as e:
        return render_template("login.html", next=next_param or "", error=f"DB error: {e}")

    # Password check: en esta versión guardamos hash plano con SHA256 en init_auth.py,
    # o un hash cualquiera que verifiques (ajusta a tu implementación real).
    import hashlib
    def check_pwd(plain, stored):
        # acepta SHA256 en hex o password plano en entorno demo
        sha = hashlib.sha256(plain.encode()).hexdigest()
        return stored in (plain, sha)

    if not user or not check_pwd(password, user["password_hash"] or ""):
        return render_template("login.html", next=next_param or "", error="Credenciales inválidas")

    session["user_id"] = user["id"]
    return redirect(next_param or url_for("panel"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------
# Claim de etiqueta
# -----------------------------
@app.route("/claim/<public_code>", methods=["GET", "POST"])
def claim(public_code):
    if not g.user:
        # debería haber sido redirigido aquí con next por /v/<code>
        return redirect(url_for("login", next=f"/claim/{public_code}"))

    # GET: confirmación simple
    if request.method == "GET":
        return render_template("claim.html", code=public_code)

    # POST: asignar la etiqueta al usuario logueado, si está libre
    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s FOR UPDATE", (public_code,))
        row = cur.fetchone()
        if not row:
            cur.close(); cnx.close()
            return "Etiqueta inexistente.", 404

        if row["user_id"] is None:
            cur.execute("""
                UPDATE qr_codes
                SET user_id=%s, claimed_at=NOW()
                WHERE id=%s
            """, (g.user["id"], row["id"]))
            cur.close(); cnx.close()
            return redirect(url_for("panel"))
        elif row["user_id"] == g.user["id"]:
            cur.close(); cnx.close()
            return redirect(url_for("panel"))
        else:
            cur.close(); cnx.close()
            return "Esta etiqueta ya fue activada por otro usuario.", 403
    except Exception as e:
        return f"Error DB: {e}", 500

# -----------------------------
# Panel del usuario
# -----------------------------
@app.route("/panel")
def panel():
    if not g.user:
        return redirect(url_for("login", next="/panel"))
    try:
        cnx = get_db(); cur = cnx.cursor(dictionary=True)
        cur.execute("""
            SELECT id, public_code
            FROM qr_codes
            WHERE user_id=%s
            ORDER BY id DESC
        """, (g.user["id"],))
        rows = cur.fetchall()
        cur.close(); cnx.close()
        return render_template("panel.html", rows=rows, user=g.user)
    except Exception as e:
        return f"Error DB: {e}", 500

# -----------------------------
# Main
# -----------------------------
if __name__ == "__main__":
    # Para desarrollo local (en Railway corre gunicorn)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=True)
