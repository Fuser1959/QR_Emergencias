# link_qr.py
import getpass
import re
import sys
from urllib.parse import urlparse
import mysql.connector

def parse_mysql_public_url(url: str):
    """
    Espera un URL del estilo:
    mysql://root:PASSWORD@shortline.proxy.rlwy.net:40635/railway
    Devuelve (host, port, db, user, password)
    """
    u = urlparse(url)
    if u.scheme != "mysql":
        raise ValueError("La URL debe comenzar con mysql://")
    host = u.hostname
    port = u.port or 3306
    db   = (u.path or "/railway").lstrip("/")
    user = u.username or "root"
    pwd  = u.password or ""
    return host, port, db, user, pwd

def ensure_emergency_data(conn, user_id):
    """
    Si el usuario no tiene emergency_data, creamos una ficha básica.
    Columnas esperadas (por tu app.py):
      nombre, apellido, telefono_1, telefono_2, factor_sanguineo, tiene_alergias, instructivo_url, user_id
    """
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM emergency_data WHERE user_id=%s LIMIT 1", (user_id,))
    has = cur.fetchone()
    if not has:
        cur.execute("""
            INSERT INTO emergency_data
            (nombre, apellido, telefono_1, telefono_2, factor_sanguineo, tiene_alergias, instructivo_url, user_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            "Juan", "Pérez", "1122334455", "1199887766",
            "0+", 0, "https://www.argentina.gob.ar/salud/primeros-auxilios",
            user_id
        ))
        conn.commit()
    cur.close()

def create_and_link_qr(conn, user_id):
    """
    Crea un nuevo registro en qr_codes para este user_id.
    Usamos el próximo id (MAX(id)+1) y generamos un qr_code_string tipo 'QR###'.
    Devuelve (new_id, qr_code_string).
    """
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(MAX(id),0) + 1 FROM qr_codes")
    next_id = cur.fetchone()[0]
    qr_string = f"QR{next_id:03d}"
    # Insert con id explícito para que el /emergencia/<id> funcione directo
    cur.execute(
        "INSERT INTO qr_codes (id, qr_code_string, user_id) VALUES (%s,%s,%s)",
        (next_id, qr_string, user_id)
    )
    conn.commit()
    cur.close()
    return next_id, qr_string

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    mysql_url = input("MYSQL_PUBLIC_URL: ").strip()
    try:
        host, port, db, user, pwd = parse_mysql_public_url(mysql_url)
    except Exception as e:
        print(f"URL inválida: {e}")
        sys.exit(1)

    email = input("Email del usuario (el que usaste para /login): ").strip()
    if not re.match(r".+@.+\..+", email):
        print("Email inválido.")
        sys.exit(1)

    print(f"→ Conectando a {host}:{port} / db={db} user={user} …")
    conn = mysql.connector.connect(host=host, port=port, user=user, password=pwd, database=db)

    # Buscamos el usuario por email
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=%s LIMIT 1", (email,))
    row = cur.fetchone()
    if not row:
        print("Ese email no existe en la tabla users. Crealo primero con init_auth.py")
        sys.exit(1)
    user_id = row[0]

    # Aseguramos que tenga emergency_data
    ensure_emergency_data(conn, user_id)

    # Creamos y vinculamos un QR
    new_id, qr_string = create_and_link_qr(conn, user_id)

    print("\nListo ✅")
    print(f"- Se creó y vinculó el QR id={new_id} (qr_code_string={qr_string}) al user_id={user_id}.")
    print(f"- Probalo en tu panel: /panel")
    print(f"- Link público directo: /emergencia/{new_id}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
