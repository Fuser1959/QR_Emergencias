import mysql.connector
from getpass import getpass
from urllib.parse import urlparse
from werkzeug.security import generate_password_hash

def parse_mysql_public_url(url: str):
    """
    Ejemplo: mysql://root:PASS@shortline.proxy.rlwy.net:40635/railway
    """
    p = urlparse(url)
    if p.scheme != "mysql":
        raise ValueError("URL inválida: debe comenzar con mysql://")
    return {
        "host": p.hostname,
        "port": p.port or 3306,
        "user": p.username or "root",
        "password": p.password or "",
        "db": p.path.lstrip("/") or "railway",
    }

def ensure_password_hash_column(conn, db_name: str):
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='users' AND COLUMN_NAME='password_hash'
    """, (db_name,))
    (count,) = cur.fetchone()
    if count == 0:
        # Agregar columna sin IF NOT EXISTS (compat.)
        cur.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL;")
    cur.close()

def get_user_id(conn, email: str):
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE email=%s", (email,))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None

def update_password(conn, uid: int, pwd_hash: str):
    cur = conn.cursor()
    cur.execute("UPDATE users SET password_hash=%s WHERE id=%s", (pwd_hash, uid))
    cur.close()

def create_user(conn, email: str, pwd_hash: str):
    """Tu esquema usa full_name (no nombre/apellido)."""
    cur = conn.cursor()
    full_name = email.split("@")[0] or "Usuario Demo"
    cur.execute(
        "INSERT INTO users (email, password_hash, full_name) VALUES (%s,%s,%s)",
        (email, pwd_hash, full_name),
    )
    cur.close()

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    url = input("MYSQL_PUBLIC_URL: ").strip()
    cfg = parse_mysql_public_url(url)

    email = input("Email del usuario a crear/actualizar (ej. demo@qr.app): ").strip().lower()
    plain = getpass("Contraseña para ese usuario: ")

    print(f"→ Conectando a {cfg['host']}:{cfg['port']} / db={cfg['db']} user={cfg['user']} …")
    conn = mysql.connector.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], database=cfg["db"]
    )
    conn.autocommit = False

    try:
        # 1) Asegurar columna password_hash si falta
        ensure_password_hash_column(conn, cfg["db"])

        # 2) Crear/actualizar usuario
        uid = get_user_id(conn, email)
        pwd_hash = generate_password_hash(plain)
        if uid:
            update_password(conn, uid, pwd_hash)
            print(f"→ Actualizado password_hash para user id={uid}")
        else:
            create_user(conn, email, pwd_hash)
            print(f"→ Creado usuario nuevo con email={email}")

        conn.commit()
        print("Listo ✅")
    except Exception as e:
        conn.rollback()
        print("ERROR:", e)
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()
