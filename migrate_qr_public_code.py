import os
# migrate_qr_public_code.py
import mysql.connector
from urllib.parse import urlparse
from secrets import choice
import sys

# Configurar via variable de entorno APP_BASE_URL o PUBLIC_BASE
APP_BASE_URL = os.environ.get(
    "APP_BASE_URL",
    os.environ.get("PUBLIC_BASE", "https://web-production-8479c.up.railway.app")
)

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/I/1 para evitar confusión
CODE_LEN = 10

def parse_mysql_public_url(url: str):
    p = urlparse(url)
    if p.scheme != "mysql":
        raise ValueError("MYSQL_PUBLIC_URL inválida (debe comenzar con mysql://)")
    return {
        "host": p.hostname,
        "port": p.port or 3306,
        "user": p.username or "root",
        "password": p.password or "",
        "database": (p.path or "/railway").lstrip("/") or "railway",
    }

def column_exists(conn, db, table, column):
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s
    """, (db, table, column))
    (cnt,) = cur.fetchone()
    cur.close()
    return cnt > 0

def index_exists(conn, db, table, index_name):
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s
    """, (db, table, index_name))
    (cnt,) = cur.fetchone()
    cur.close()
    return cnt > 0

def gen_code(n=CODE_LEN):
    return "".join(choice(ALPHABET) for _ in range(n))

def generate_unique_code(conn):
    """Genera un public_code que no exista en qr_codes."""
    cur = conn.cursor()
    while True:
        code = gen_code()
        cur.execute("SELECT 1 FROM qr_codes WHERE public_code=%s LIMIT 1", (code,))
        if cur.fetchone() is None:
            cur.close()
            return code

def backfill_public_codes(conn):
    cur = conn.cursor()
    cur.execute("SELECT id FROM qr_codes WHERE public_code IS NULL OR public_code=''")
    rows = cur.fetchall()
    if not rows:
        cur.close()
        return 0

    count = 0
    for (qr_id,) in rows:
        code = generate_unique_code(conn)
        cur2 = conn.cursor()
        cur2.execute("UPDATE qr_codes SET public_code=%s WHERE id=%s", (code, qr_id))
        cur2.close()
        count += 1
        if count % 50 == 0:
            conn.commit()
    conn.commit()
    cur.close()
    return count

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    url = input("MYSQL_PUBLIC_URL: ").strip()
    cfg = parse_mysql_public_url(url)

    print(f"→ Conectando a {cfg['host']}:{cfg['port']} / db={cfg['database']} …")
    conn = mysql.connector.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], database=cfg["database"]
    )
    try:
        # 1) Agregar columnas si faltan
        if not column_exists(conn, cfg["database"], "qr_codes", "public_code"):
            print("→ Agregando columna qr_codes.public_code …")
            cur = conn.cursor()
            cur.execute("ALTER TABLE qr_codes ADD COLUMN public_code VARCHAR(24) NULL;")
            cur.close()
            conn.commit()

        if not column_exists(conn, cfg["database"], "qr_codes", "claimed_at"):
            print("→ Agregando columna qr_codes.claimed_at …")
            cur = conn.cursor()
            cur.execute("ALTER TABLE qr_codes ADD COLUMN claimed_at DATETIME NULL;")
            cur.close()
            conn.commit()

        # 2) Crear índice único para public_code si falta
        if not index_exists(conn, cfg["database"], "qr_codes", "public_code"):
            print("→ Creando índice único en qr_codes.public_code …")
            cur = conn.cursor()
            cur.execute("CREATE UNIQUE INDEX public_code ON qr_codes(public_code);")
            cur.close()
            conn.commit()

        # 3) Backfill de códigos para filas existentes
        print("→ Generando códigos para filas sin public_code …")
        added = backfill_public_codes(conn)
        print(f"→ Filas actualizadas: {added}")

        # 4) Muestra para control visual
        cur = conn.cursor()
        cur.execute("SELECT id, public_code FROM qr_codes ORDER BY id LIMIT 5")
        sample = cur.fetchall()
        cur.close()
        if sample:
            print("\nMuestra:")
            for (qid, code) in sample:
                print(f"  id={qid}  public_code={code}  URL={APP_BASE_URL}/v/{code}")

        print("\nListo ✅")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
