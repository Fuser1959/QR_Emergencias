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

        # Nota: acepta 'QR001' o el id numérico
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
        # Mostrar error legible en lugar de 500
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
            .card { border-radius: 15px; padding: 30px; box-shadow: 0 0 20px rg
