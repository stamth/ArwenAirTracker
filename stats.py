import logging
import datetime
from db import db

logger = logging.getLogger(__name__)

def get_stats_aeronave(matricula):
    with db.connection_scope() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute('''
            SELECT 
                COUNT(id) as total_vuelos, SUM(costo_usd) as total_costo_usd,
                SUM(consumo_fuel_l) as total_consumo_fuel_l, SUM(emisiones_co2_kg) as total_emisiones_co2_kg,
                SUM(distancia_km) as total_distancia_km
            FROM vuelos WHERE matricula = %s
        ''' if db.is_postgres else '''
            SELECT 
                COUNT(id) as total_vuelos, SUM(costo_usd) as total_costo_usd,
                SUM(consumo_fuel_l) as total_consumo_fuel_l, SUM(emisiones_co2_kg) as total_emisiones_co2_kg,
                SUM(distancia_km) as total_distancia_km
            FROM vuelos WHERE matricula = ?
        ''', (matricula,))
        res = cursor.fetchone()
        if not res or res['total_vuelos'] == 0: return None
        return dict(res)

def get_ranking_gasto(limit=10):
    with db.connection_scope() as conn:
        cursor = db.get_cursor(conn)
        cursor.execute('''
            SELECT matricula, SUM(costo_usd) as total_gastos_usd
            FROM vuelos GROUP BY matricula ORDER BY total_gastos_usd DESC LIMIT %s
        ''' if db.is_postgres else '''
            SELECT matricula, SUM(costo_usd) as total_gastos_usd
            FROM vuelos GROUP BY matricula ORDER BY total_gastos_usd DESC LIMIT ?
        ''', (limit,))
        return [dict(r) for r in cursor.fetchall()]

# FIX: Agregar parametro limite
def get_ultimas_posiciones(limite=50):
    return db.get_ultimas_posiciones(limite=limite)

def get_destinos_frecuentes(matricula=None):
    with db.connection_scope() as conn:
        cursor = db.get_cursor(conn)
        ph = "%s" if db.is_postgres else "?"
        query = "SELECT matricula, origen_nombre, destino_nombre, COUNT(*) as cantidad FROM vuelos "
        params = []
        if matricula:
            query += f" WHERE matricula = {ph} "
            params.append(matricula)
        query += " GROUP BY matricula, origen_nombre, destino_nombre ORDER BY cantidad DESC LIMIT 15"
        cursor.execute(query, params)
        return [dict(r) for r in cursor.fetchall()]

def get_conteo_detectados():
    return db.get_conteo_detectados()

def get_resumen_semanal():
    with db.connection_scope() as conn:
        cursor = db.get_cursor(conn)
        if db.is_postgres:
            sql_totales = "SELECT COUNT(id) as total_vuelos, SUM(costo_usd) as total_usd, SUM(distancia_km) as total_km, SUM(consumo_fuel_l) as total_fuel, SUM(emisiones_co2_kg) as total_co2 FROM vuelos WHERE aterrizaje_utc::timestamp >= NOW() - INTERVAL %s"
            params = ('7 days',)
            sql_gastador = "SELECT matricula, COUNT(id) as c, SUM(costo_usd) as usd FROM vuelos WHERE aterrizaje_utc::timestamp >= NOW() - INTERVAL %s GROUP BY matricula ORDER BY usd DESC LIMIT 1"
        else:
            sql_totales = "SELECT COUNT(id) as total_vuelos, SUM(costo_usd) as total_usd, SUM(distancia_km) as total_km, SUM(consumo_fuel_l) as total_fuel, SUM(emisiones_co2_kg) as total_co2 FROM vuelos WHERE datetime(aterrizaje_utc) >= datetime('now', ?)"
            params = ('-7 days',)
            sql_gastador = "SELECT matricula, COUNT(id) as c, SUM(costo_usd) as usd FROM vuelos WHERE datetime(aterrizaje_utc) >= datetime('now', ?) GROUP BY matricula ORDER BY usd DESC LIMIT 1"
        cursor.execute(sql_totales, params)
        totales = cursor.fetchone()
        if not totales or totales['total_vuelos'] == 0: return None
        cursor.execute(sql_gastador, params)
        mas_gastador = cursor.fetchone()
        return {"totales": dict(totales), "mas_gastador": dict(mas_gastador) if mas_gastador else None}
