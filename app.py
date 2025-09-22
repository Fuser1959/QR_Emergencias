from flask import Flask, render_template_string, jsonify
import mysql.connector
from mysql.connector import Error
import json
import os

app = Flask(__name__)

# -------- Config DB por variables de entorno (ideal para nube) --------
DB_HOST = os.environ.get("QR_DB_HOST", "localhost")
DB_USER = os.environ.get("QR_DB_USER", "root")
DB_PASS = os.environ.get("QR_DB_PASSWORD", "")
DB_NAME = os.environ.get("QR_DB_NAME", "qr_emergencias")

db_config = {
    'host': DB_HOST,
    'user': DB_USER,
    'password': DB_PASS,
    'database': DB_NAME,
    # 'port': int(os.environ.get("QR_DB_PORT", "3306")),  # no necesario en Railway (3306)
}

# -------- Cargar JSON con teléfonos de emergencia --------
BASE_JSON_PATH = os.path.join(os.path.dirname(__file__), "static", "emergency_numbers_partial_updated.json")
with open(BASE_JSON_PATH, "r", encoding="utf-8") as f:
    emergency_numbers = json.load(f)

# -------- Healthcheck para despliegue --------
@app.get("/health")
def health():
    return {"status": "ok"}, 200

# -------- Ping a la base para diagnóstico --------
@app.get("/db_ping")
def db_ping():
    try:
        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        return jsonify({
            "db_host": DB_HOST,
            "db_name": DB_NAME,
            "status": "db_ok"
        }), 200
    except Error as e:
        return jsonify({
            "db_host": DB_HOST,
            "db_name": DB_NAME,
            "status": "db_error",
            "error": str(e)
        }), 500

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
        # Mostrar error legible en lugar de 500 genérico
        return f"Error de base de datos: {e}", 500

    if not data:
        return "No se encontraron datos para este código / No data found for this code."

    html_template = '''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <title>Datos de Emergencia / Emergency Data</title>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
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

if __name__ == "__main__":
    # Para uso local con Flask (dev). En la nube usaremos Gunicorn (o el runner de la plataforma).
    app.run(debug=True)
