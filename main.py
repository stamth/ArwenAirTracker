import asyncio
import logging
import signal
import sys
import os
import datetime
import time
from dotenv import load_dotenv

# Forzar IPv4 para evitar timeouts de IPv6 en servidores con IPv6 roto o sin ruteo externo
import socket
orig_getaddrinfo = socket.getaddrinfo
def forced_ipv4_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if family == socket.AF_UNSPEC:
        family = socket.AF_INET
    return orig_getaddrinfo(host, port, family, type, proto, flags)
socket.getaddrinfo = forced_ipv4_getaddrinfo

load_dotenv()

import logging.handlers

# Configuración de logging con rotación horaria en RAM (/dev/shm)
log_path = "/dev/shm/aerobot_debug.log" if os.name != 'nt' else "debug.log"
log_handler = logging.handlers.TimedRotatingFileHandler(
    log_path, when="H", interval=1, backupCount=24
)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[log_handler, logging.StreamHandler(sys.stdout)]
)

# Silenciar logs ruidosos
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

import shutil
# --- CONFIGURACIÓN DE BASE DE DATOS EN RAM ---
DB_ORIGINAL = "aerobot.db"
DB_RAM = "/dev/shm/aerobot.db"
USE_RAM_DB = os.name != 'nt' # Solo en Linux

if USE_RAM_DB:
    try:
        if os.path.exists(DB_ORIGINAL):
            shutil.copy2(DB_ORIGINAL, DB_RAM)
            logging.info(f"[SISTEMA] Base de datos copiada a RAM: {DB_RAM}")
        else:
            logging.warning(f"[SISTEMA] No se encontró {DB_ORIGINAL}, se creará una nueva en RAM.")
        os.environ["DB_PATH"] = DB_RAM
    except Exception as e:
        logging.error(f"[SISTEMA] Error al copiar DB a RAM: {e}. Usando disco.")
        USE_RAM_DB = False

from db import db
from tracker import Tracker
from notificador import Notificador
from bot_interactivo import BotInteractivo
from matriculas import AERONAVES_DATA, MATRICULA_TO_ICAO24

logger = logging.getLogger("AerobotMain")

async def tracker_staggered_task(tracker):
    logger.info("[SISTEMA] Hilo del Tracker Escalonado iniciado.")
    
    # Airplanes.live: Barrido rotativo de 7 zonas (dist=250 NM max permitido por la API)
    # Cobertura total de Argentina: lat -22 a -55, lon -53 a -73
    STEP_SECONDS = 12  # 7 pasos x 12s = 84s + margen para latencia de red
    zonas_live = [
        {"nombre": "NOA",             "lat": -24.0, "lon": -65.0, "dist": 250},  # Jujuy, Salta, Tucumán, Catamarca
        {"nombre": "NEA",             "lat": -28.0, "lon": -56.0, "dist": 250},  # Misiones, Corrientes, Formosa, Chaco
        {"nombre": "CENTRO",          "lat": -33.0, "lon": -63.0, "dist": 250},  # Córdoba, Santa Fe, Entre Ríos, San Luis
        {"nombre": "AMBA/CUYO",       "lat": -34.0, "lon": -67.5, "dist": 250},  # Buenos Aires, Mendoza, San Juan, La Pampa
        {"nombre": "PATAGONIA NORTE", "lat": -41.0, "lon": -68.0, "dist": 250},  # Neuquén, Río Negro
        {"nombre": "PATAGONIA SUR",   "lat": -49.0, "lon": -69.0, "dist": 250},  # Santa Cruz, Chubut sur
        {"nombre": "TIERRA DEL FUEGO","lat": -54.5, "lon": -68.0, "dist": 250},  # Ushuaia, TdF, Atlántico Sur
    ]
    
    # Conos de precisión para ADSB.fi / ADSB.lol (Alta eficiencia en zonas clave)
    conos = [
        {"nombre": "AMBA/CENTRO", "lat": -34.6, "lon": -58.5},
        {"nombre": "CORDOBA/NORTE", "lat": -31.3, "lon": -64.2},
        {"nombre": "PATAGONIA/ANDES", "lat": -41.1, "lon": -71.3}
    ]
    
    iteration = 0
    while True:
        try:
            start_time = time.time()
            iteration += 1
            
            logger.info(f"=== INICIANDO BARRIDO GLOBAL N° {iteration} ===")
            
            # Obtener lista de aviones conocidos para búsquedas HEX
            flota = db.get_all_aeronaves(solo_activas=True)
            icao_list = [a['icao24'] for a in flota if a['icao24']]
            
            # Conos rotativos para las APIs secundarias
            idx_cono_fi = (iteration - 1) % 3
            idx_cono_lol = iteration % 3
            
            # Bucle interno: Barremos las 7 zonas de Airplanes.live en pasos de 13 segundos
            for i, zona in enumerate(zonas_live):
                step_start = time.time()
                
                # 1. Siempre consultamos la zona correspondiente de Airplanes.live
                ac_list = await tracker.fetch_airplanes_live(lat=zona['lat'], lon=zona['lon'], dist=zona['dist'])
                tot, ofis = await tracker.process_detected(ac_list)
                logger.info(f"[RADAR] Paso {i+1}/7: Airplanes.live (ZONA:{zona['nombre']}) -> {tot} aviones ({len(ofis)} ofis)")
                
                # 2. Intercalamos las otras APIs en los primeros 4 pasos
                if i == 0:
                    cono = conos[idx_cono_fi]
                    ac_list = await tracker.fetch_adsb_fi(lat=cono['lat'], lon=cono['lon'], dist=250)
                    tot, ofis = await tracker.process_detected(ac_list)
                    logger.info(f"[RADAR] Paso 1/7: + ADSB.fi (CONO:{cono['nombre']}) -> {tot} aviones ({len(ofis)} ofis)")
                
                elif i == 1:
                    cono = conos[idx_cono_lol]
                    ac_list = await tracker.fetch_adsb_lol(lat=cono['lat'], lon=cono['lon'], dist=250)
                    tot, ofis = await tracker.process_detected(ac_list)
                    logger.info(f"[RADAR] Paso 2/7: + ADSB.lol (CONO:{cono['nombre']}) -> {tot} aviones ({len(ofis)} ofis)")
                
                elif i == 2:
                    ac_list = await tracker.fetch_adsb_lol_mil()
                    tot, ofis = await tracker.process_detected(ac_list)
                    logger.info(f"[RADAR] Paso 3/7: + ADSB.lol (MIL) -> {tot} aviones ({len(ofis)} ofis)")
                
                elif i == 3:
                    ac_list_live = await tracker.fetch_airplanes_live_hex(icao_list)
                    tot_live, ofis_live = await tracker.process_detected(ac_list_live)
                    logger.info(f"[RADAR] Paso 4/7: + Airplanes.live-HEX (CONOCIDOS) -> {tot_live} aviones ({len(ofis_live)} ofis)")
                    
                    ac_list_os = await tracker.fetch_opensky(icao24_list=icao_list)
                    if ac_list_os is not None:
                        tot_os, ofis_os = await tracker.process_detected(ac_list_os)
                        logger.info(f"[RADAR] Paso 4/7: + OpenSky (CONOCIDOS) -> {tot_os} aviones ({len(ofis_os)} ofis)")
                
                # Esperamos hasta cumplir los 13 segundos del paso actual
                elapsed_step = time.time() - step_start
                sleep_time = max(0, STEP_SECONDS - elapsed_step)
                await asyncio.sleep(sleep_time)
            
            # Cálculo de espera final para sincronizar el ciclo
            elapsed = time.time() - start_time
            wait_time = max(0, 90 - elapsed)
            if wait_time > 0:
                logger.info(f"[RADAR] Ciclo completado en {elapsed:.1f}s. Esperando {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
            
            # Purga cada 10 ciclos
            if iteration % 10 == 0:
                purged_smart = await tracker.check_ghost_landings()
                count = db.purge_ghost_vuelos(horas=8)
                if count > 0 or purged_smart > 0: 
                    logger.info(f"[DB] Purgados {count} vuelos colgados y {purged_smart} aterrizajes inteligentes.")
                    
            # Mantenimiento profundo diario (aprox cada 1000 ciclos)
            if iteration % 1000 == 0:
                pos_borradas = db.purge_old_positions(days=15)
                cand_borradas = db.purge_old_candidatas(hours=72)
                logger.info(f"[DB-MANTENIMIENTO] Borradas {pos_borradas} posiciones antiguas del disco y {cand_borradas} candidatas expiradas.")

            # Heartbeat cada 10 minutos
            if iteration % 10 == 0:
                mem_n = len(tracker.hourly_stats["Norte"]["total"])
                mem_s = len(tracker.hourly_stats["Sur"]["total"])
                logger.info(f"[HEARTBEAT] Bot vivo. Aeronaves en RAM: {mem_n + mem_s}. Ciclos: {iteration}")

            # Cálculo de espera real
            elapsed = time.time() - start_time
            wait_time = max(0, 90 - elapsed)
            logger.info(f"[RADAR] Ciclo completado en {elapsed:.1f}s. Esperando {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
            
        except Exception as e:
            logger.error(f"[TRACKER] Error en ciclo {iteration}: {e}", exc_info=True)
            await asyncio.sleep(30)

async def hourly_status_task(tracker, notificador):
    logger.info("[CLOCK] Tarea de reporte horario iniciada.")
    while True:
        try:
            now = datetime.datetime.now()
            wait_seconds = 3600 - (now.minute * 60 + now.second)
            if wait_seconds < 10: wait_seconds += 3600
            
            logger.info(f"[CLOCK] Proximo reporte horario en {wait_seconds} segundos.")
            await asyncio.sleep(wait_seconds)
            
            # Consultar vuelos activos (aviones en seguimiento ahora mismo)
            vuelos_all = db.get_vuelos_activos()
            
            # Filtrar solo aeronaves que hayan reportado posición en los últimos 15 minutos
            vuelos_activos = []
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            for v in vuelos_all:
                try:
                    last_upd = datetime.datetime.fromisoformat(v.get('last_update', ''))
                    if last_upd.tzinfo is None: last_upd = last_upd.replace(tzinfo=datetime.timezone.utc)
                    diff = (now_utc - last_upd).total_seconds() / 60
                    if diff <= 15: # Límite de 15 minutos de inactividad
                        vuelos_activos.append(v)
                except:
                    continue

            if not vuelos_activos:
                logger.info("[CLOCK] Sin aeronaves activas en los últimos 15 min. Reporte horario omitido.")
                continue
            
            # Construir lista de aeronaves en seguimiento
            now_arg = now_utc - datetime.timedelta(hours=3)
            msg = f"🕒 <b>SEGUIMIENTO ACTIVO</b> - {now_arg.strftime('%H:%M')} ARG\n\n"
            
            # Cachear aeronaves para no consultar DB en cada iteración del for
            aeronaves_cache = {a['matricula']: a.get('nombre', a['matricula']) for a in db.get_all_aeronaves(solo_activas=False)}
            
            for v in vuelos_activos:
                mat = v.get('matricula', '?')
                nombre = aeronaves_cache.get(mat, mat)
                
                origen = v.get('origen_nombre', v.get('origen_ciudad', '?'))
                
                # Calcular tiempo en vuelo
                try:
                    dt_desp = datetime.datetime.fromisoformat(v.get('despegue_utc', ''))
                    if dt_desp.tzinfo is None:
                        dt_desp = dt_desp.replace(tzinfo=datetime.timezone.utc)
                    mins = int((datetime.datetime.now(datetime.timezone.utc) - dt_desp).total_seconds() / 60)
                    dur_str = f"{mins // 60}h {mins % 60}min" if mins >= 60 else f"{mins}min"
                except:
                    dur_str = "?"
                
                msg += f"✈️ <b>{nombre}</b> (<code>{mat}</code>)\n"
                msg += f"    📍 Desde: {origen} | ⏱️ {dur_str}\n\n"
            
            msg += f"📡 {len(vuelos_activos)} aeronave{'s' if len(vuelos_activos) > 1 else ''} en radar"
            
            await notificador.alertar_especial(msg, throttle_key="hourly_report")
            
            # Sincronización de DB a disco cada hora (Si estamos en modo RAM)
            if USE_RAM_DB:
                logger.info("[CLOCK] Sincronizando Base de Datos de RAM a Disco...")
                db.backup_to_disk(DB_ORIGINAL)
                
        except Exception as e:
            logger.error(f"[MAIN] Error reporte: {e}")
            await asyncio.sleep(60)

async def run_bot_and_tracker():
    logger.info("--- Iniciando ArwenAirTracker (Modo Híbrido Estabilizado) ---")
    db.seed_db(AERONAVES_DATA, MATRICULA_TO_ICAO24)
    
    notificador = Notificador()
    tracker = Tracker(notificador)
    bot = BotInteractivo()
    
    # Alerta de Inicio en Telegram
    await notificador.alertar_especial("🚀 <b>ARWEN AIR TRACKER ONLINE</b>\n\nEl sistema híbrido de rastreo ha comenzado a operar.\nModo: Rotación Cruzada (N/S)\nFuentes: 4 APIs Activas")
    
    tasks = [
        tracker_staggered_task(tracker), 
        bot.run_async(), 
        hourly_status_task(tracker, notificador)
    ]
    
    logger.info("[SISTEMA] Verificando credenciales de APIs...")
    opensky_status = await tracker.verify_auth()
    twitter_ok = notificador.verify_auth()
    
    if opensky_status == "OK" and twitter_ok:
        logger.info("[SISTEMA] ✅ Credenciales cargadas correctamente de OpenSky y Twitter.")
    else:
        if opensky_status == "OK": logger.info("[SISTEMA] ✅ OpenSky: Conexión exitosa.")
        elif opensky_status == "INVALID": logger.error("[SISTEMA] ❌ OpenSky: Usuario o Contraseña incorrectos.")
        elif opensky_status == "RATE_LIMIT": logger.warning("[SISTEMA] ⚠️ OpenSky: Límite de cuota alcanzado (pero las credenciales parecen estar bien).")
        elif opensky_status == "MISSING": logger.warning("[SISTEMA] ⚠️ OpenSky: No configurado en .env")
        else: logger.error(f"[SISTEMA] ❌ OpenSky: Error de conexión ({opensky_status})")
        
        if twitter_ok: logger.info("[SISTEMA] ✅ Twitter: Conexión exitosa.")
        else: logger.error("[SISTEMA] ❌ Twitter: Error de autenticación.")
        
    logger.info("[SISTEMA] Iniciando Tracker + Bot + Reportes...")
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("[SISTEMA] Parada solicitada. Apagando...")
    finally:
        if USE_RAM_DB:
            logger.info("[SISTEMA] Sincronización FINAL de DB a Disco antes de salir...")
            db.backup_to_disk(DB_ORIGINAL)

if __name__ == "__main__":
    if os.name != 'nt':
        # Auto-limpieza agresiva de otras instancias antes de iniciar para evitar conflictos de Telegram o DB
        my_pid = os.getpid()
        cleanup_cmd = f"pgrep -f 'main.py' | grep -v {my_pid} | xargs kill -9 2>/dev/null || true"
        os.system(cleanup_cmd)
        time.sleep(1.0) # Esperar a que se liberen sockets/puertos/recursos

    try:
        asyncio.run(run_bot_and_tracker())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.critical(f"FATAL: {e}")
        sys.exit(1)
