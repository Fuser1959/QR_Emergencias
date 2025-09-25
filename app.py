# =========================================
# QR Emergencias - app.py
# =========================================
# - Vista pública por ID interno:           /emergencia/<id>
# - Vista por código público (QR físico):   /v/<public_code>
#     * Si no está activado => redirige a /login?next=/claim/<code>
#     * Si está activado    => redirige a /emergencia/<id>
# - Reclamo/activación de etiqueta:         /claim/<code>
# - Autenticación básica:                   /login, /logout
# - Panel del usuario (lista sus QRs):      /panel
# - Salud y ping a DB:                      /health, /db_ping
# =========================================

from flask import (
    Flask, render_template_string, request, redirect, url_for, session, jsonify
)
import os
import json
from datetime import datetime
import mysql.connector
from mysql.connector import Error as MySQLError
from werkzeug.security import check_password_hash

# -----------------------------------------
# App & configuración base
# -----------------------------------------
app = Flask(__name__)

# Clave de sesión (en producción poné un valor fuerte via env)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# Config de base de datos desde variables de entorno (Railway)
DB_HOST = os.environ.get("QR_DB_HOST", "localhost")
DB_USER = os.environ.get("QR_DB_USER", "root")
DB_PASS = os.environ.get("QR_DB_PASSWORD", "")
DB_NAME = os.environ.get("QR_DB_NAME", "qr_emergencias")

db_config = {
    "host": DB_HOST,
    "user": DB_USER,
    "password": DB_PASS,
    "database": DB_NAME,
    "autocommit": True,
}

# Base pública para generar URLs (opcional)
BASE_PUBLIC_URL = os.environ.get("BASE_PUBLIC_URL", "")

# Path del JSON de números de emergencia (carpeta 'static' en minúsculas)
BASE_DIR = os.path.dirname(__file__)
EMERGENCY_JSON = os.path.join(BASE_DIR, "static", "emergency_numbers_partial_updated.json")
with open(EMERGENCY_JSON, "r", encoding="utf-8") as f:
    EMERGENCY_NUMBERS = json.load(f)

# -----------------------------------------
# Helpers de DB y sesión
# -----------------------------------------
def get_conn():
    """Devuelve una conexión MySQL usando la config global."""
    return mysql.connector.connect(**db_config)

def get_current_user():
    """Devuelve el usuario logueado (o None)."""
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    # full_name: si nombre+apellido está vacío, usar email
    cur.execute(
        """
        SELECT id,
               email,
               COALESCE(NULLIF(TRIM(CONCAT(nombre, ' ', apellido)), ''), email) AS full_name
        FROM users
        WHERE id=%s
        """,
        (uid,),
    )
    user = cur.fetchone()
    cur.close()
    conn.close()
    return user

# -----------------------------------------
# Plantilla base y vistas inline (para simplicidad)
# -----------------------------------------
TPL_BASE = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>{{ title or "QR Emergencias" }}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f5f6f8; font-family: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Liberation Sans", sans-serif; }
    .wrap { max-width: 860px; margin: 40px auto; }
    .card { border-radius: 16px; box-shadow: 0 10px 28px rgba(0,0,0,.06); padding: 28px; }
    .btn-call { font-weight: 600; width: 100%; margin-bottom: 8px; }
    .emergency-box { margin-top: 20px; padding: 16px; background: #f1f3f5; border-left: 6px solid #dc3545; border-radius: 10px; }
    .muted { color: #6c757d; }
    code { font-size: .95rem; }
  </style>
</head>
<body>
  <div class="wrap">
    {% block body %}{% endblock %}
  </div>
</body>
</html>
"""

# --- Vista pública de emergencia (ficha) ---
TPL_EMERGENCIA = """
{% extends base %}
{% block body %}
<div class="card">
  <h2 class="text-center mb-2">🚨 Datos de Emergencia / Emergency Data</h2>
  <p class="text-center text-muted mb-4">Accedé a la información crítica de forma rápida / Access critical information quickly</p>

  <div class="row">
    <div class="col-12 col-md-6">
      <p><strong>Nombre / Name:</strong> {{ data.nombre }} {{ data.apellido }}</p>
      <p><strong>Grupo sanguíneo / Blood group:</strong> {{ data.factor_sanguineo }}</p>
      <p><strong>¿Tiene alergias? / Has allergies?:</strong> {{ "Sí / Yes" if data.tiene_alergias else "No / No" }}</p>
    </div>
    <div class="col-12 col-md-6">
      <p><strong>Teléfonos / Phones</strong></p>
      <a class="btn btn-danger btn-call" href="tel:{{ data.telefono_1 }}">📞 Llamar al contacto 1 / Call contact 1</a>
      <a class="btn btn-warning btn-call" href="tel:{{ data.telefono_2 }}">📞 Llamar al contacto 2 / Call contact 2</a>
    </div>
  </div>

  <hr class="my-3">

  <a class="btn btn-info btn-call" target="_blank" href="{{ data.instructivo_url }}">▶️ Ver instructivo de primeros auxilios / See first aid instructions</a>

  <div class="emergency-box mt-3" id="emergencyNumbers">
    <strong>Números de emergencia locales / Local emergency numbers:</strong>
    <div id="ubicacion">Cargando ubicación / Loading location...</div>
  </div>
</div>

<script>
  // Diccionario embebido con números de emergencia
  const emergencyNumbers = {{ emergency_numbers|tojson }};

  function renderNumbers(country, region) {
    let nums;
    try {
      const byCountry = emergencyNumbers[country];
      nums = (region && byCountry[region]) ? byCountry[region] : byCountry.default;
    } catch (e) {
      // fallback genérico
      nums = { "policía":"911", "bomberos":"100", "ambulancia":"107" };
    }
    const html = `📍 ${region || country}<br>
      Policía / Police: ${nums.policía} · Bomberos / Fire: ${nums.bomberos} · Ambulancia / Ambulance: ${nums.ambulancia}`;
    document.getElementById("ubicacion").innerHTML = html;
  }

  function reverseGeocode(lat, lon) {
    fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`)
      .then(r => r.json())
      .then(data => {
        const country = data?.address?.country || "Argentina";
        const region = data?.address?.state || null;
        renderNumbers(country, region);
      })
      .catch(() => {
        document.getElementById("ubicacion").innerText = "No se pudo determinar la ubicación / Could not determine location";
      });
  }

  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      pos => reverseGeocode(pos.coords.latitude, pos.coords.longitude),
      ()  => document.getElementById("ubicacion").innerText = "No se pudo acceder a la ubicación del dispositivo / Cannot access device location"
    );
  } else {
    document.getElementById("ubicacion").innerText = "Tu navegador no soporta geolocalización / Your browser does not support geolocation";
  }
</script>
{% endblock %}
"""

# --- Login ---
TPL_LOGIN = """
{% extends base %}
{% block body %}
<div class="card" style="max-width:480px;margin:0 auto;">
  <h4 class="text-center mb-3">Iniciar sesión</h4>
  {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
  <form method="post">
    <div class="mb-3">
      <label class="form-label">Email</label>
      <input type="email" name="email" class="form-control" required autofocus>
    </div>
    <div class="mb-3">
      <label class="form-label">Contraseña</label>
      <input type="password" name="password" class="form-control" required>
    </div>
    <button class="btn btn-primary w-100">Entrar</button>
  </form>
  <div class="text-center mt-3">
    <a class="small" href="{{ url_for('home') }}">← Volver al inicio</a>
  </div>
</div>
{% endblock %}
"""

# --- Panel del usuario ---
TPL_PANEL = """
{% extends base %}
{% block body %}
<div class="card">
  <div class="d-flex justify-content-between align-items-center">
    <h4 class="mb-0">Tus Códigos QR</h4>
    <div class="text-end">
      <span class="me-2 muted">{{ user.email }}</span>
      <a class="btn btn-sm btn-outline-secondary" href="{{ url_for('logout') }}">Salir</a>
    </div>
  </div>
  <hr>
  {% if not items %}
    <div class="alert alert-info">Todavía no tenés QR asociados. Podemos cargarlos desde consola por ahora.</div>
  {% else %}
    <div class="table-responsive">
      <table class="table table-sm align-middle">
        <thead><tr><th>#</th><th>QR interno</th><th>Código público</th><th>Reclamado</th><th>Ver</th></tr></thead>
        <tbody>
        {% for it in items %}
          <tr>
            <td>{{ loop.index }}</td>
            <td>{{ it.qr_code_string }}</td>
            <td><code>{{ it.public_code }}</code></td>
            <td>{{ it.claimed_at or "-" }}</td>
            <td>
              <a class="btn btn-sm btn-outline-primary" target="_blank"
                 href="{{ url_for('view_by_public_code', public_code=it.public_code) }}">/v/{{ it.public_code }}</a>
            </td>
          </tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  {% endif %}
  <p class="small text-muted mt-2">Tip: pegá ese link en el QR físico.</p>
</div>
{% endblock %}
"""

# --- Reclamo de etiqueta ---
TPL_CLAIM = """
{% extends base %}
{% block body %}
<div class="card" style="max-width:640px;margin:0 auto;">
  <h4>Reclamar etiqueta</h4>
  {% if msg %}<div class="alert alert-info">{{ msg }}</div>{% endif %}
  <p class="mb-1"><strong>Código público:</strong> <code>{{ code }}</code></p>
  {% if already %}
    <div class="alert alert-warning mt-3">Este código ya fue reclamado por otro usuario.</div>
    <a class="btn btn-secondary" href="{{ url_for('panel') }}">Ir a mi panel</a>
  {% else %}
    <form method="post" class="mt-3">
      <button class="btn btn-primary">Reclamar y asociar a mi cuenta</button>
      <a class="btn btn-outline-secondary ms-2" href="{{ url_for('panel') }}">Cancelar</a>
    </form>
  {% endif %}
</div>
{% endblock %}
"""

# -----------------------------------------
# Rutas de sistema (home / health / db_ping)
# -----------------------------------------
@app.route("/")
def home():
    return "¡Bienvenido a QR Emergencias! / Welcome to Emergency QR!"

@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/db_ping")
def db_ping():
    """Prueba simple de conexión a la base de datos."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT DATABASE()")
        db = cur.fetchone()[0]
        cur.close()
        conn.close()
        return jsonify({"status": "db_ok", "db_host": DB_HOST, "db_name": db})
    except MySQLError as e:
        return jsonify({"status": "db_error", "error": str(e), "db_host": DB_HOST, "db_name": DB_NAME}), 500

# -----------------------------------------
# Vista pública tradicional por ID interno
# -----------------------------------------
@app.route("/emergencia/<int:codigo_id>")
def emergencia(codigo_id: int):
    """
    Renderiza la ficha pública usando el ID interno de qr_codes.
    También tolera que el link llegue como QRxxx por compatibilidad.
    """
    try:
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT ed.nombre, ed.apellido, ed.telefono_1, ed.telefono_2,
                   ed.factor_sanguineo, ed.tiene_alergias, ed.instructivo_url
            FROM qr_codes qc
            JOIN emergency_data ed ON ed.user_id = qc.user_id
            WHERE qc.id = %s OR qc.qr_code_string = %s
            LIMIT 1
            """,
            (codigo_id, f"QR{codigo_id:03d}"),
        )
        data = cur.fetchone()
        cur.close()
        conn.close()

        if not data:
            return "No se encontraron datos para este código / No data found for this code.", 404

        return render_template_string(
            TPL_EMERGENCIA,
            base=TPL_BASE,
            data=data,
            emergency_numbers=EMERGENCY_NUMBERS,
            title="Datos de Emergencia",
        )
    except MySQLError as e:
        return f"Error de base de datos: {e}", 500

# -----------------------------------------
# NUEVO FLUJO: /v/<public_code>
# -----------------------------------------
@app.route("/v/<public_code>")
def view_by_public_code(public_code: str):
    """
    Si el QR (qr_codes.public_code) YA está activado (user_id != NULL),
    redirige a la ficha pública /emergencia/<id>.
    Si NO está activado:
      - sin sesión: redirige a /login?next=/claim/<code>
      - con sesión: redirige directo a /claim/<code>
    """
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT id AS qr_id, user_id FROM qr_codes WHERE public_code=%s LIMIT 1",
        (public_code,),
    )
    qr = cur.fetchone()
    cur.close()
    conn.close()

    if not qr:
        return "Código no encontrado.", 404

    if qr["user_id"] is not None:
        # Activado ⇒ mostrar ficha (usamos la vista por ID interno)
        return redirect(url_for("emergencia", codigo_id=qr["qr_id"]))

    # No activado ⇒ flujo de claim
    target = url_for("claim_qr", code=public_code)
    if not session.get("user_id"):
        # Forzamos login con 'next' para volver a claim
        return redirect(url_for("login") + "?next=" + target)
    return redirect(target)

# -----------------------------------------
# Reclamar / activar etiqueta
# -----------------------------------------
@app.route("/claim/<code>", methods=["GET", "POST"])
def claim_qr(code: str):
    """
    El usuario logueado reclama el código público (asigna user_id y claimed_at).
    Si no está logueado, se lo manda a /login con 'next' de vuelta a /claim/<code>.
    """
    user = get_current_user()
    if not user:
        return redirect(url_for("login") + "?next=" + url_for("claim_qr", code=code))

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, user_id FROM qr_codes WHERE public_code=%s LIMIT 1", (code,))
    row = cur.fetchone()

    if not row:
        cur.close()
        conn.close()
        return render_template_string(TPL_CLAIM, base=TPL_BASE, code=code, already=True, msg="El código no existe.")

    if row["user_id"] is not None:
        cur.close()
        conn.close()
        return render_template_string(TPL_CLAIM, base=TPL_BASE, code=code, already=True, msg="Este código ya fue reclamado.")

    if request.method == "POST":
        # Reclamar (solo si sigue sin dueño)
        cur2 = conn.cursor()
        cur2.execute(
            "UPDATE qr_codes SET user_id=%s, claimed_at=%s WHERE id=%s AND user_id IS NULL",
            (user["id"], datetime.utcnow(), row["id"]),
        )
        conn.commit()
        cur2.close()
        cur.close()
        conn.close()
        return redirect(url_for("panel"))

    # GET: pantalla de confirmación
    cur.close()
    conn.close()
    return render_template_string(TPL_CLAIM, base=TPL_BASE, code=code, already=False, msg=None)

# -----------------------------------------
# Autenticación: login / logout
# -----------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Login mínimo:
    - users.email (texto)
    - users.password_hash (bcrypt/werkzeug)
    """
    next_url = request.args.get("next") or url_for("panel")

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        passwd = request.form.get("password", "")

        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, email, password_hash FROM users WHERE email=%s LIMIT 1", (email,))
        u = cur.fetchone()
        cur.close()
        conn.close()

        if not u or not u["password_hash"] or not check_password_hash(u["password_hash"], passwd):
            return render_template_string(TPL_LOGIN, base=TPL_BASE, error="Credenciales inválidas", title="Login")

        session["user_id"] = u["id"]
        return redirect(next_url)

    # GET
    return render_template_string(TPL_LOGIN, base=TPL_BASE, error=None, title="Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# -----------------------------------------
# Panel del usuario (ver sus QRs)
# -----------------------------------------
@app.route("/panel")
def panel():
    user = get_current_user()
    if not user:
        return redirect(url_for("login") + "?next=" + url_for("panel"))

    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT id, qr_code_string, public_code, claimed_at
        FROM qr_codes
        WHERE user_id=%s
        ORDER BY id
        """,
        (user["id"],),
    )
    items = cur.fetchall()
    cur.close()
    conn.close()

    return render_template_string(
        TPL_PANEL,
        base=TPL_BASE,
        user=user,
        items=items,
        title="Panel",
    )

# -----------------------------------------
# Main local (en Railway se usa Gunicorn)
# -----------------------------------------
if __name__ == "__main__":
    # Desarrollo local
    app.run(debug=True, host="0.0.0.0", port=5000)
