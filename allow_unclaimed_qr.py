# allow_unclaimed_qr.py — hace que qr_codes.user_id permita NULL (para etiquetas no reclamadas)
import mysql.connector
from urllib.parse import urlparse

def parse_mysql_public_url(url: str):
    u = urlparse(url)
    if u.scheme != "mysql":
        raise ValueError("MYSQL_PUBLIC_URL inválida (debe empezar con mysql://)")
    return {
        "host": u.hostname,
        "port": u.port or 3306,
        "user": u.username or "root",
        "password": u.password or "",
        "database": (u.path or "/railway").lstrip("/") or "railway",
    }

def main():
    print("Pegá tu MYSQL_PUBLIC_URL (Railway → MySQL → Variables):")
    url = input("MYSQL_PUBLIC_URL: ").strip()
    cfg = parse_mysql_public_url(url)

    conn = mysql.connector.connect(**cfg)
    cur = conn.cursor(dictionary=True)

    # 1) Leer definición actual de la columna user_id
    cur.execute("""
        SELECT COLUMN_TYPE, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='qr_codes' AND COLUMN_NAME='user_id'
    """, (cfg["database"],))
    row = cur.fetchone()
    if not row:
        cur.close(); conn.close()
        print("No existe la columna user_id en qr_codes.")
        return

    coltype = row["COLUMN_TYPE"]           # ej: "bigint", "int", "bigint unsigned"
    is_nullable = row["IS_NULLABLE"]       # "YES" / "NO"

    print(f"→ user_id tipo actual: {coltype} | NULLABLE: {is_nullable}")

    if is_nullable == "YES":
        print("Nada que hacer: user_id ya permite NULL ✅")
        cur.close(); conn.close()
        return

    # 2) Quitar NOT NULL manteniendo tipo
    alter_sql = f"ALTER TABLE qr_codes MODIFY user_id {coltype} NULL"
    print(f"→ Ejecutando: {alter_sql}")
    cur2 = conn.cursor()
    cur2.execute(alter_sql)
    conn.commit()
    cur2.close()
    cur.close(); conn.close()
    print("Listo ✅ — user_id ahora permite NULL.")

if __name__ == "__main__":
    main()
