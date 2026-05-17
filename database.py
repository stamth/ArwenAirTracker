import sqlite3
import os
import logging
import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.environ.get("DATABASE_URL") or os.environ.get("DB_PATH") or "aerobot.db"
        self.db_path = db_path
        self.is_postgres = self.db_path.startswith("postgres")
        self._init_db()

    @contextmanager
    def connection_scope(self):
        if self.is_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            conn = psycopg2.connect(self.db_path)
            conn.autocommit = True
            try: yield conn
            finally: conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
            finally: conn.close()

    def get_cursor(self, conn):
        if self.is_postgres:
            from psycopg2.extras import RealDictCursor
            return conn.cursor(cursor_factory=RealDictCursor)
        return conn.cursor()

    def _init_db(self):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            
            # Optimizaciones para SQLite (WAL y Sincronizacion Normal)
            if not self.is_postgres:
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA cache_size = -5000") # 5MB de cache
                
            # Tablas básicas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aeronaves (
                    matricula TEXT PRIMARY KEY,
                    nombre TEXT, organismo TEXT, provincia TEXT, marca TEXT, modelo TEXT,
                    precio_usd REAL, costo_hora_usd REAL, litros_hora_estimado REAL,
                    co2_kg_hora_estimado REAL, icao24 TEXT, activa INTEGER DEFAULT 1
                )
            ''')
            
            schema_vuelos = '''
                CREATE TABLE IF NOT EXISTS vuelos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT, icao24 TEXT, callsign TEXT,
                    origen_icao TEXT, origen_nombre TEXT, origen_ciudad TEXT, origen_pais TEXT,
                    destino_icao TEXT, destino_nombre TEXT, destino_ciudad TEXT, destino_pais TEXT,
                    despegue_utc TEXT, aterrizaje_utc TEXT, duracion_min INTEGER,
                    distancia_km REAL, costo_usd REAL, consumo_fuel_l REAL, emisiones_co2_kg REAL,
                    es_internacional INTEGER, es_finde INTEGER, es_nocturno INTEGER, tweet_id TEXT
                )
            '''
            if self.is_postgres:
                schema_vuelos = schema_vuelos.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            cursor.execute(schema_vuelos)

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS vuelos_activos (
                    matricula TEXT PRIMARY KEY,
                    icao24 TEXT, origen_icao TEXT, origen_nombre TEXT, origen_ciudad TEXT,
                    despegue_utc TEXT, despegue_lat REAL, despegue_lon REAL,
                    last_lat REAL, last_lon REAL, last_alt REAL, last_update TEXT
                )
            ''')
            
            schema_posiciones = '''
                CREATE TABLE IF NOT EXISTS posiciones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    matricula TEXT, icao24 TEXT, lat REAL, lon REAL, alt REAL, vel REAL,
                    en_vuelo INTEGER, timestamp_utc TEXT
                )
            '''
            if self.is_postgres:
                schema_posiciones = schema_posiciones.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
            cursor.execute(schema_posiciones)

            cursor.execute('CREATE TABLE IF NOT EXISTS usuarios_autorizados (user_id INTEGER PRIMARY KEY, username TEXT, fecha_alta TEXT)')
            cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS aeronaves_candidatas (
                    callsign TEXT PRIMARY KEY, icao24 TEXT, pais TEXT,
                    primer_avistamiento TEXT, ultimo_avistamiento TEXT, veces_visto INTEGER DEFAULT 1
                )
            ''')

    def seed_db(self, aeronaves_data, matricula_to_icao):
        """Siembra datos iniciales usando nombres de columnas para evitar errores de indice."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT COUNT(*) as c FROM aeronaves")
            if cursor.fetchone()['c'] == 0:
                logger.info("[DB] Sembrando datos iniciales...")
                # Definimos el orden de los campos en AERONAVES_DATA de matriculas.py
                fields = [
                    "matricula", "nombre", "organismo", "provincia", 
                    "marca", "modelo", "precio_usd", "costo_hora_usd", 
                    "litros_hora_estimado", "co2_kg_hora_estimado"
                ]
                for item in aeronaves_data:
                    # Mapear los datos de la lista al diccionario de columnas
                    data = dict(zip(fields, item))
                    data["icao24"] = matricula_to_icao.get(data["matricula"], "").lower()
                    data["activa"] = 1
                    
                    cols = ", ".join(data.keys())
                    vals = ", ".join(["%s" if self.is_postgres else ":" + k for k in data.keys()])
                    cursor.execute(f"INSERT INTO aeronaves ({cols}) VALUES ({vals})", data)

    # --- METODOS DE VUELOS ---
    def purge_ghost_vuelos(self, horas=12):
        """Purga vuelos que no han reportado posicion en X horas."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            limit_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=horas)).isoformat()
            
            if self.is_postgres:
                sql = "DELETE FROM vuelos_activos WHERE last_update < %s"
            else:
                # En SQLite comparamos strings ISO directos (el orden alfabetico coincide con el temporal)
                sql = "DELETE FROM vuelos_activos WHERE last_update < ?"
            
            cursor.execute(sql, (limit_time,))
            return cursor.rowcount

    def add_vuelo_activo(self, mat, icao, orig_icao, orig_n, orig_c, start_utc, lat, lon, alt):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            # Asegurar formato ISO UTC
            if isinstance(start_utc, datetime.datetime):
                if start_utc.tzinfo is None: start_utc = start_utc.replace(tzinfo=datetime.timezone.utc)
                start_utc = start_utc.isoformat()
                
            sql = "INSERT INTO vuelos_activos (matricula, icao24, origen_icao, origen_nombre, origen_ciudad, despegue_utc, despegue_lat, despegue_lon, last_lat, last_lon, last_alt, last_update) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)" if self.is_postgres else "INSERT INTO vuelos_activos (matricula, icao24, origen_icao, origen_nombre, origen_ciudad, despegue_utc, despegue_lat, despegue_lon, last_lat, last_lon, last_alt, last_update) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            cursor.execute(sql, (mat, icao, orig_icao, orig_n, orig_c, start_utc, lat, lon, lat, lon, alt, start_utc))

    def get_vuelo_activo(self, mat):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM vuelos_activos WHERE matricula = %s" if self.is_postgres else "SELECT * FROM vuelos_activos WHERE matricula = ?", (mat,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_vuelos_activos(self):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM vuelos_activos")
            return [dict(r) for r in cursor.fetchall()]

    def update_vuelo_activo_posicion(self, mat, lat, lon, alt, now_str):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("UPDATE vuelos_activos SET last_lat=%s, last_lon=%s, last_alt=%s, last_update=%s WHERE matricula=%s" if self.is_postgres else "UPDATE vuelos_activos SET last_lat=?, last_lon=?, last_alt=?, last_update=? WHERE matricula=?", (lat, lon, alt, now_str, mat))

    def remove_vuelo_activo(self, mat):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("DELETE FROM vuelos_activos WHERE matricula = %s" if self.is_postgres else "DELETE FROM vuelos_activos WHERE matricula = ?", (mat,))

    def save_vuelo(self, v):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cols = ", ".join(v.keys())
            placeholders = ", ".join(["%s" if self.is_postgres else "?" for _ in v])
            sql = f"INSERT INTO vuelos ({cols}) VALUES ({placeholders})"
            if self.is_postgres:
                sql += " RETURNING id"
                cursor.execute(sql, list(v.values()))
                return cursor.fetchone()['id']
            else:
                cursor.execute(sql, list(v.values()))
                return cursor.lastrowid

    def set_setting(self, key, val):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            sql = "INSERT INTO settings (key, value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value" if self.is_postgres else "INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)"
            cursor.execute(sql, (key, val))

    def get_setting(self, key, default=None):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT value FROM settings WHERE key = %s" if self.is_postgres else "SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row['value'] if row else default

    def get_all_aeronaves(self, solo_activas=True):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            if solo_activas: cursor.execute("SELECT * FROM aeronaves WHERE activa = 1 ORDER BY matricula")
            else: cursor.execute("SELECT * FROM aeronaves ORDER BY matricula")
            return [dict(r) for r in cursor.fetchall()]

    def save_posicion(self, mat, icao, lat, lon, alt, vel, en_vuelo, ts):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            sql = "INSERT INTO posiciones (matricula, icao24, lat, lon, alt, vel, en_vuelo, timestamp_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)" if self.is_postgres else "INSERT INTO posiciones (matricula, icao24, lat, lon, alt, vel, en_vuelo, timestamp_utc) VALUES (?,?,?,?,?,?,?,?)"
            cursor.execute(sql, (mat, icao, lat, lon, alt, vel, en_vuelo, ts))

    def save_aeronave_candidata(self, callsign, icao, pais, ts):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT callsign, veces_visto FROM aeronaves_candidatas WHERE callsign = %s" if self.is_postgres else "SELECT callsign, veces_visto FROM aeronaves_candidatas WHERE callsign = ?", (callsign,))
            row = cursor.fetchone()
            if row:
                v = (row['veces_visto'] or 1) + 1
                cursor.execute("UPDATE aeronaves_candidatas SET ultimo_avistamiento=%s, veces_visto=%s WHERE callsign=%s" if self.is_postgres else "UPDATE aeronaves_candidatas SET ultimo_avistamiento=?, veces_visto=? WHERE callsign=?", (ts, v, callsign))
                return False
            else:
                cursor.execute("INSERT INTO aeronaves_candidatas (callsign, icao24, pais, primer_avistamiento, ultimo_avistamiento, veces_visto) VALUES (%s,%s,%s,%s,%s,1)" if self.is_postgres else "INSERT INTO aeronaves_candidatas (callsign, icao24, pais, primer_avistamiento, ultimo_avistamiento, veces_visto) VALUES (?,?,?,?,?,1)", (callsign, icao, pais, ts, ts))
                return True

    def get_ultimas_posiciones(self, limite=15):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM posiciones ORDER BY timestamp_utc DESC LIMIT %s" if self.is_postgres else "SELECT * FROM posiciones ORDER BY timestamp_utc DESC LIMIT ?", (limite,))
            return [dict(r) for r in cursor.fetchall()]

    def get_conteo_detectados(self):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT COUNT(*) as count FROM vuelos_activos")
            return cursor.fetchone()['count']

    def delete_stats_aeronave(self, matricula):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("DELETE FROM vuelos WHERE matricula = %s" if self.is_postgres else "DELETE FROM vuelos WHERE matricula = ?", (matricula,))
            cursor.execute("DELETE FROM posiciones WHERE matricula = %s" if self.is_postgres else "DELETE FROM posiciones WHERE matricula = ?", (matricula,))

    def purge_old_positions(self, days=15):
        """Elimina registros de posiciones GPS más antiguos que 'days' para no saturar el disco."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            cursor.execute("DELETE FROM posiciones WHERE timestamp_utc < %s" if self.is_postgres else "DELETE FROM posiciones WHERE timestamp_utc < ?", (cutoff,))
            count = cursor.rowcount
            return count

    def purge_old_candidatas(self, hours=24):
        """Elimina aeronaves candidatas que no han sido vistas en más de X horas."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
            cursor.execute("DELETE FROM aeronaves_candidatas WHERE ultimo_avistamiento < %s" if self.is_postgres else "DELETE FROM aeronaves_candidatas WHERE ultimo_avistamiento < ?", (cutoff,))
            return cursor.rowcount

    def add_usuario_autorizado(self, user_id, username):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            now = datetime.datetime.now(datetime.timezone.utc).isoformat()
            cursor.execute("INSERT INTO usuarios_autorizados (user_id, username, fecha_alta) VALUES (%s,%s,%s) ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username" if self.is_postgres else "INSERT OR REPLACE INTO usuarios_autorizados (user_id, username, fecha_alta) VALUES (?,?,?)", (user_id, username, now))

    def remove_usuario_autorizado(self, user_id):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("DELETE FROM usuarios_autorizados WHERE user_id = %s" if self.is_postgres else "DELETE FROM usuarios_autorizados WHERE user_id = ?", (user_id,))

    def get_usuarios_autorizados(self):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM usuarios_autorizados")
            return [dict(r) for r in cursor.fetchall()]

    def get_aeronaves_candidatas(self):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM aeronaves_candidatas ORDER BY veces_visto DESC")
            return [dict(r) for r in cursor.fetchall()]

    def update_aeronave_status(self, matricula, activa=1):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("UPDATE aeronaves SET activa = %s WHERE matricula = %s" if self.is_postgres else "UPDATE aeronaves SET activa = ? WHERE matricula = ?", (activa, matricula))

    def get_aeronave(self, matricula):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT * FROM aeronaves WHERE matricula = %s" if self.is_postgres else "SELECT * FROM aeronaves WHERE matricula = ?", (matricula,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_aeronave(self, data):
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cols = ", ".join(data.keys())
            if self.is_postgres:
                vals = ", ".join(["%s" for _ in data])
                set_clause = ", ".join([f"{k} = EXCLUDED.{k}" for k in data.keys() if k != "matricula"])
                sql = f"INSERT INTO aeronaves ({cols}) VALUES ({vals}) ON CONFLICT (matricula) DO UPDATE SET {set_clause}"
            else:
                vals = ", ".join([f":{k}" for k in data.keys()])
                sql = f"INSERT OR REPLACE INTO aeronaves ({cols}) VALUES ({vals})"
            cursor.execute(sql, data)

    # --- METODOS PARA INFORMES ---
    def get_vuelos_historial(self, limit=5000):
        """Obtiene todos los vuelos históricos ordenados por fecha."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT v.*, a.nombre, a.organismo, a.modelo FROM vuelos v LEFT JOIN aeronaves a ON v.matricula = a.matricula ORDER BY v.despegue_utc DESC LIMIT %s" if self.is_postgres else "SELECT v.*, a.nombre, a.organismo, a.modelo FROM vuelos v LEFT JOIN aeronaves a ON v.matricula = a.matricula ORDER BY v.despegue_utc DESC LIMIT ?", (limit,))
            return [dict(r) for r in cursor.fetchall()]

    def get_vuelos_por_matricula(self, mat, limit=5000):
        """Obtiene todos los vuelos de una matrícula específica."""
        with self.connection_scope() as conn:
            cursor = self.get_cursor(conn)
            cursor.execute("SELECT v.*, a.nombre, a.organismo, a.modelo FROM vuelos v LEFT JOIN aeronaves a ON v.matricula = a.matricula WHERE v.matricula = %s ORDER BY v.despegue_utc DESC LIMIT %s" if self.is_postgres else "SELECT v.*, a.nombre, a.organismo, a.modelo FROM vuelos v LEFT JOIN aeronaves a ON v.matricula = a.matricula WHERE v.matricula = ? ORDER BY v.despegue_utc DESC LIMIT ?", (mat, limit))
            return [dict(r) for r in cursor.fetchall()]

    def backup_to_disk(self, disk_path="aerobot.db"):
        """Sincroniza la base de datos actual (sea RAM o disco) a un archivo específico."""
        if self.is_postgres: return
        
        try:
            # Usar el API de backup de SQLite para una copia segura y no corrupta
            import sqlite3 as sqlite_module
            with sqlite_module.connect(disk_path) as disk_conn:
                with self.connection_scope() as ram_conn:
                    ram_conn.backup(disk_conn)
            logger.info(f"[DB-BACKUP] Sincronización a disco ({disk_path}) completada con éxito.")
            return True
        except Exception as e:
            logger.error(f"[DB-BACKUP] Error al sincronizar a disco: {e}")
            return False

db = Database()

