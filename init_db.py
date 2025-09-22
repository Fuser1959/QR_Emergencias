import mysql.connector
from mysql.connector import Error
from getpass import getpass

# >>> Conexión pública de Railway (según tu MYSQL_PUBLIC_URL):
HOST = "shortline.proxy.rlwy.net"  # aparece en tu MYSQL_PUBLIC_URL
PORT = 40635                       # aparece en tu MYSQL_PUBLIC_URL
USER = "root"                      # aparece en tu MYSQL_PUBLIC_URL
DB   = "railway"                   # aparece en tu MYSQLPUBLIC_URL
QR_CODE_DEMO = "QR001"

DDL_AND_SEED = """
CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(190) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  full_name VARCHAR(190),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS qr_codes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  qr_code_string VARCHAR(190) UNIQUE NOT NULL,
  user_id INT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS emergency_data (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  nombre VARCHAR(100) NOT NULL,
  apellido VARCHAR(100) NOT NULL,
  telefono_1 VARCHAR(40),
  telefono_2 VARCHAR(40),
  factor_sanguineo VARCHAR(10),
  tiene_alergias BOOLEAN DEFAULT FALSE,
  instructivo_url VARCHAR(255),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

INSERT INTO users (email, password_hash, full_name)
VALUES ('demo@qr.com', 'hash-demo', 'Usuario Demo')
ON DUPLICATE KEY UPDATE full_name=VALUES(full_name);
"""

def main():
    print("Conexión a MySQL (Railway - proxy público)")
    password = getpass("Pegá la contraseña de MYSQLPASSWORD y presioná Enter (no se mostrará): ")

    cfg = dict(host=HOST, port=PORT, user=USER, password=password, database=DB)

    try:
        print("→ Conectando…")
        cnx = mysql.connector.connect(**cfg)
        cnx.autocommit = True
        cur = cnx.cursor()

        print("→ Creando tablas y datos demo…")
        for stmt in [s.strip() for s in DDL_AND_SEED.split(";\n") if s.strip()]:
            cur.execute(stmt)

        # usuario demo
        cur.execute("SELECT id FROM users WHERE email=%s", ("demo@qr.com",))
        (uid,) = cur.fetchone()

        # QR demo si no existe
        cur.execute("INSERT IGNORE INTO qr_codes (qr_code_string, user_id) VALUES (%s, %s)", (QR_CODE_DEMO, uid))

        # emergency_data si no existe
        cur.execute("SELECT 1 FROM emergency_data WHERE user_id=%s", (uid,))
        if cur.fetchone() is None:
            cur.execute("""
                INSERT INTO emergency_data
                (user_id, nombre, apellido, telefono_1, telefono_2, factor_sanguineo, tiene_alergias, instructivo_url)
                VALUES (%s, 'Juan', 'Pérez', '+5491100000001', '+5491100000002', '0+', FALSE,
                        'https://www.cruzroja.org.ar/primeros-auxilios')
            """, (uid,))

        cur.execute("SELECT id, qr_code_string, user_id FROM qr_codes ORDER BY id")
        rows = cur.fetchall()
        print("\nQR codes existentes:")
        for r in rows:
            print(f"  id={r[0]} | qr_code_string={r[1]} | user_id={r[2]}")

        if rows:
            first_id = rows[0][0]
            print(f"\nAbrí esta URL en el navegador:")
            print(f"https://web-production-8479c.up.railway.app/emergencia/{first_id}")
        else:
            print("\nNo se encontraron QR; revisá los logs.")

        print("\nListo ✅")
    except Error as e:
        print("ERROR MySQL:", e)
        raise
    finally:
        try:
            cur.close()
            cnx.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
