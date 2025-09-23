from flask import (
    Flask, render_template_string, request, redirect, url_for,
    session, g, abort
)
import mysql.connector
import json
import os
from werkzeug.security import check_password_hash

app = Flask(__name__)

# =========================
# Config por variables de entorno
# =========================
DB_HOST = os.environ.get("QR_DB_HOST", "localhost")
DB_USER = os.environ.get("QR_DB_USER", "root")
DB_PASS = os.environ.get("QR_DB_PASSWORD", "")
DB_NAME = os.environ.get("QR_DB_NAME", "qr_emergencias")

# Clave de sesión Flask
app.secret_key = os.environ.get("QR_SECRET_KEY", "dev-please-change-me")

db_config = {
    'host': DB_HOST,
    'user': DB_USER,
    'password': DB_PASS,
    'database': DB_NAME
}

# =========================
# Cargar JSON con teléfonos de emergencia
# =========================
BASE_JSON_PATH = os.path.join(os.path.dirname(__file__), "static", "emergency_numbers_partial_updated.json")
with open(BASE_JSON_PATH, "r", encoding="utf-8") as f:
    emergency_numbers = json.load(f)

# =========================
# Helpers DB y auth
# =========================
def get_conn():
    return mysql.connector.connect(**db_config)

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, email, COALESCE(full_name, CONCAT_WS(' ', nombre, apellido)) AS full_name FROM users WHERE id=%s", (uid,))
    user = cur.fetchone()
    cur.close(); conn.close()
    return user

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def load_user():
    g.user = get_current_user()

# =========================
# Rutas base / salud / diagnóstico
# =========================
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/db_ping")
def db_ping():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.close(); conn.close()
        return {"status": "db_ok", "db_host": DB_HOST, "db_name": DB_NAME}
    except Exception as e:
        return {"status": "db_error", "db_host": DB_HOST, "db_name": DB_NAME, "error": str(e)}

@app.route("/")
def home():
    return "¡Bienvenido a QR Emergencias / Welcome to Emergency QR!"

# =========================
# Login / Logout / Panel
# =========================
LOGIN_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Ingresar / Login</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container" style="max-width: 420px;">
    <div class="card shadow mt-5">
      <div class="card-body p-4">
        <h3 class="mb-3 text-center">Iniciar sesión</h3>
        {% if error %}<div class="alert alert-danger py-2">{{ error }}</div>{% endif %}
        <form method="post">
          <div class="mb-3">
            <label class="form-label">Email</label>
            <input name="email" type="email" class="form-control" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label">Contraseña</label>
            <input name="password" type="password" class="form-control" required>
          </div>
          <button class="btn btn-primary w-100">Entrar</button>
        </form>
        <p class="text-center mt-3 mb-0"><a href="{{ url_for('home') }}" class="text-decoration-none">← Volver al inicio</a></p>
      </div>
    </div>
  </div>
</body>
</html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, email, password_hash FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close(); conn.close()

        if not user or not user.get("password_hash"):
            return render_template_string(LOGIN_HTML, error="Usuario o contraseña inválidos.")
        if not check_password_hash(user["password_hash"], password):
            return render_template_string(LOGIN_HTML, error="Usuario o contraseña inválidos.")

        session["user_id"] = user["id"]
        next_url = request.args.get("next") or url_for("panel")
        return redirect(next_url)

    return render_template_string(LOGIN_HTML, error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

PANEL_HTML = """
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>Panel</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light">
  <div class="container" style="max-width: 820px;">
    <div class="d-flex justify-content-between align-items-center mt-4">
      <h3 class="mb-0">Tus Códigos QR</h3>
      <div>
        <span class="me-3 text-muted">{{ user_email }}</span>
        <a class="btn btn-outline-secondary btn-sm" href="{{ url_for('logout') }}">Salir</a>
      </div>
    </div>

    {% if qrs %}
      <div class="list-group mt-3">
        {% for qr in qrs %}
          <a class="list-group-item list-group-item-action d-flex justify-content-between align-items-center"
             href="{{ url_for('emergencia', codigo_id=qr.id) }}" target="_blank">
            <div>
              <div class="fw-semibold">{{ qr.qr_code_string }}</div>
              <small class="text-muted">QR ID: {{ qr.id }}</small>
            </div>
            <span class="badge bg-primary rounded-pill">ver ficha</span>
          </a>
        {% endfor %}
      </div>
    {% else %}
      <div class="alert alert-info mt-4">
        Todavía no tenés QR asociados. Podemos cargar uno desde consola por ahora.
      </div>
    {% endif %}

    <hr class="my-4">
    <p class="small text-muted">
      Tip: compartí el link de cada ficha pública para pegarlo en tu QR físico.
    </p>
  </div>
</body>
</html>
"""

@app.route("/panel")
@login_required
def panel():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, qr_code_string FROM qr_codes WHERE user_id=%s ORDER BY id", (g.user["id"],))
    qrs = cur.fetchall()
    cur.close(); conn.close()
    return render_template_string(PANEL_HTML, qrs=qrs, user_email=g.user["email"])

# =========================
# Vista pública de emergencia
# =========================
@app.route("/emergencia/<int:codigo_id>")
def emergencia(codigo_id):
    try:
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT ed.nombre, ed.apellido, ed.telefono_1, ed.telefono_2,
                   ed.factor_sanguineo, ed.tiene_alergias, ed.instructivo_url
            FROM qr_codes qc
            JOIN emergency_data ed ON qc.user_id = ed.user_id
            WHERE qc.qr_code_string = %s OR qc.id = %s
        """, (f"QR00{codigo_id:01X}", codigo_id))

        data = cursor.fetchone()
        cursor.close(); conn.close()
    except Exception as e:
        return f"Error de base de datos: {e}"

    if not data:
        return "No se encontraron datos para este código / No data found for this code."

    html_template = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Datos de Emergencia / Emergency Data</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
            .container { max-width: 700px; margin-top: 40px; }
            .card { border-radius: 15px; padding: 30px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }
            .btn-call { font-size: 1.05rem; font-weight: 500; margin-bottom: 10px; width: 100%; }
            .emergency-box { margin-top: 25px; padding: 20px; background-color: #f1f1f1; border-left: 6px solid #dc3545; border-radius: 8px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h2 class="text-center mb-4">🚨 Datos de Emergencia / Emergency Data</h2>
                <p class="text-center text-muted">Accedé a la información crítica de forma rápida / Access critical information quickly</p>

                <p><strong>Nombre / Name:</strong> {{ nombre }} {{ apellido }}</p>
                <p><strong>Grupo sanguíneo / Blood group:</strong> {{ factor_sanguineo }}</p>
                <p><strong>¿Tiene alergias? / Has allergies?:</strong> {{ "Sí / Yes" if tiene_alergias else "No / No" }}</p>

                <p class="mt-4"><strong>Teléfonos de contacto / Contact phone numbers:</strong></p>
                <a href="tel:{{ telefono_1 }}" class="btn btn-danger btn-call">📞 Llamar al contacto 1 / Call contact 1</a>
                <a href="tel:{{ telefono_2 }}" class="btn btn-warning btn-call">📞 Llamar al contacto 2 / Call contact 2</a>

                <hr>
                <a href="{{ instructivo_url }}" target="_blank" class="btn btn-info btn-call">▶️ Ver instructivo de primeros auxilios / See first aid instructions</a>

                <div class="emergency-box mt-4" id="emergencyNumbers">
                    <strong>Números de emergencia locales / Local emergency numbers:</strong>
                    <div id="ubicacion">Cargando ubicación / Loading location...</div>
                </div>
            </div>
        </div>

        <script>
            const emergencyNumbers = {{ emergency_numbers|tojson }};

            function mostrarNumeros(pais, region) {
                let numeros;
                try {
                    const infoPais = emergencyNumbers[pais];
                    if (region && infoPais[region]) {
                        numeros = infoPais[region];
                    } else {
                        numeros = infoPais.default;
                    }
                } catch {
                    numeros = { "policía":"911", "bomberos":"100", "ambulancia":"107" };
                }

                let html = `📍 ${region || pais}<br>
                    Policía / Police: ${numeros.policía} · Bomberos / Fire: ${numeros.bomberos} · Ambulancia / Ambulance: ${numeros.ambulancia}`;
                document.getElementById("ubicacion").innerHTML = html;
            }

            function obtenerProvincia(lat, lon) {
                fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}`)
                    .then(response => response.json())
                    .then(data => {
                        const pais = data?.address?.country || "Argentina";
                        const region = data?.address?.state || null;
                        mostrarNumeros(pais, region);
                    })
                    .catch(() => {
                        document.getElementById("ubicacion").innerText = "No se pudo determinar la ubicación / Could not determine location";
                    });
            }

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    pos => obtenerProvincia(pos.coords.latitude, pos.coords.longitude),
                    () => document.getElementById("ubicacion").innerText = "No se pudo acceder a la ubicación del dispositivo / Cannot access device location"
                );
            } else {
                document.getElementById("ubicacion").innerText = "Tu navegador no soporta geolocalización / Your browser does not support geolocation";
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_template, **data, emergency_numbers=emergency_numbers)

# =========================
# Main (desarrollo local)
# =========================
if __name__ == "__main__":
    app.run(debug=True)
