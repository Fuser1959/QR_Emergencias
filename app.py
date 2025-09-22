from flask import Flask, render_template_string, jsonify, request
import mysql.connector
from mysql.connector import Error
import json
import os
import requests

app = Flask(__name__)

# ---------------- DB (Railway) ----------------
DB_HOST = os.environ.get("QR_DB_HOST", "localhost")
DB_USER = os.environ.get("QR_DB_USER", "root")
DB_PASS = os.environ.get("QR_DB_PASSWORD", "")
DB_NAME = os.environ.get("QR_DB_NAME", "qr_emergencias")

db_config = {
    "host": DB_HOST,
    "user": DB_USER,
    "password": DB_PASS,
    "database": DB_NAME,
}

# ---------------- Nominatim ----------------
# Sugerido: en Railway → web → Variables, agregar NOMINATIM_EMAIL con tu email real
NOMINATIM_EMAIL = os.environ.get("NOMINATIM_EMAIL")  # p.ej. "nicolas.gimenez.asta.ng@gmail.com"
NOMINATIM_BASE = "https://nominatim.openstreetmap.org/reverse"

def _nominatim_headers():
    # User-Agent recomendado por Nominatim: incluir app e email de contacto si está disponible
    if NOMINATIM_EMAIL:
        ua = f"QR-Emergencias/1.0 (contact:{NOMINATIM_EMAIL})"
    else:
        ua = "QR-Emergencias/1.0 (no-email-provided)"
    return {
        "User-Agent": ua,
        "Accept": "application/json",
        # Opcionalmente podrías incluir Referer, pero no es obligatorio.
    }

# ---------------- Cargar JSON con teléfonos ----------------
BASE_JSON_PATH = os.path.join(os.path.dirname(__file__), "static", "emergency_numbers_partial_updated.json")
with open(BASE_JSON_PATH, "r", encoding="utf-8") as f:
    emergency_numbers = json.load(f)

# ---------------- Healthcheck ----------------
@app.get("/health")
def health():
    return {"status": "ok"}, 200

# ---------------- Diagnóstico DB ----------------
@app.get("/db_ping")
def db_ping():
    try:
        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        return jsonify({"db_host": DB_HOST, "db_name": DB_NAME, "status": "db_ok"}), 200
    except Error as e:
        return jsonify({"db_host": DB_HOST, "db_name": DB_NAME, "status": "db_error", "error": str(e)}), 500

# ---------------- Proxy a Nominatim ----------------
@app.get("/geo/reverse")
def geo_reverse():
    """
    Proxy simple: /geo/reverse?lat=...&lon=...
    Devuelve JSON de Nominatim (format=jsonv2) limitado a los campos útiles.
    """
    lat = request.args.get("lat")
    lon = request.args.get("lon")

    # Validaciones rápidas
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return jsonify({"error": "lat/lon inválidos"}), 400

    params = {
        "format": "jsonv2",
        "lat": f"{lat_f:.6f}",
        "lon": f"{lon_f:.6f}",
        "addressdetails": 1,
    }

    try:
        r = requests.get(NOMINATIM_BASE, params=params, headers=_nominatim_headers(), timeout=6)
        r.raise_for_status()
        data = r.json() if r.content else {}

        # Extraer solo lo necesario para el front
        address = data.get("address", {}) if isinstance(data, dict) else {}
        country = address.get("country")
        state = address.get("state") or address.get("region")

        return jsonify({
            "country": country,
            "state": state,
            "raw": data  # útil para debug; si no lo querés, podés quitar este campo
        }), 200

    except requests.exceptions.RequestException as e:
        return jsonify({"error": f"Nominatim error: {e}"}), 502

# ---------------- App ----------------
@app.route("/")
def home():
    return "¡Bienvenido a QR Emergencias / Welcome to Emergency QR!"

@app.route("/emergencia/<int:codigo_id>")
def emergencia(codigo_id):
    # Conexión a MySQL con manejo de errores
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        # Acepta 'QR001' o el id numérico
        cursor.execute("""
            SELECT ed.nombre, ed.apellido, ed.telefono_1, ed.telefono_2,
                   ed.factor_sanguineo, ed.tiene_alergias, ed.instructivo_url
            FROM qr_codes qc
            JOIN emergency_data ed ON qc.user_id = ed.user_id
            WHERE qc.qr_code_string = %s OR qc.id = %s
        """, (f"QR00{codigo_id:01X}", codigo_id))

        data = cursor.fetchone()
        conn.close()
    except Error as e:
        return f"Error de base de datos: {e}", 500

    if not data:
        return "No se encontraron datos para este código / No data found for this code."

    html_template = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Datos de Emergencia / Emergency Data</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background-color: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
            .container { max-width: 700px; margin-top: 50px; }
            .card { border-radius: 15px; padding: 30px; box-shadow: 0 0 20px rgba(0,0,0,0.1); }
            .btn-call { font-size: 1.1rem; font-weight: 500; margin-bottom: 10px; width: 100%; }
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
                // Ahora llamamos al backend propio (mismo dominio) => sin CORS
                fetch(`/geo/reverse?lat=${lat}&lon=${lon}`)
                    .then(response => response.json())
                    .then(data => {
                        const pais = data?.country || "Argentina";
                        const region = data?.state || null;
                        mostrarNumeros(pais, region);
                    })
                    .catch(() => {
                        document.getElementById("ubicacion").innerText =
                          "No se pudo determinar la ubicación / Could not determine location";
                    });
            }

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    pos => obtenerProvincia(pos.coords.latitude, pos.coords.longitude),
                    () => document.getElementById("ubicacion").innerText =
                        "No se pudo acceder a la ubicación del dispositivo / Cannot access device location"
                );
            } else {
                document.getElementById("ubicacion").innerText =
                    "Tu navegador no soporta geolocalización / Your browser does not support geolocation";
            }
        </script>
    </body>
    </html>
    '''
    return render_template_string(html_template, **data, emergency_numbers=emergency_numbers)

if __name__ == "__main__":
    app.run(debug=True)
