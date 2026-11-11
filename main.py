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
import shutil

import gzip
import glob

# Logging en disco: un archivo por día (logs/aerobot.log.AAAA-MM-DD.gz), 90 días de historial.
# bot_run.log (stdout) queda solo para errores y crasheos.
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
LOG_DIAS = 90
os.makedirs(LOG_DIR, exist_ok=True)
log_path = os.path.join(LOG_DIR, "aerobot.log")

def _log_rotator(source, dest):
    with open(source, "rb") as f_in, gzip.open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(source)
    # Borrar los días más viejos que LOG_DIAS
    limite = time.time() - LOG_DIAS * 86400
    for viejo in glob.glob(os.path.join(LOG_DIR, "aerobot.log.*.gz")):
        try:
            if os.path.getmtime(viejo) < limite:
                os.remove(viejo)
        except OSError:
            pass

log_handler = logging.handlers.TimedRotatingFileHandler(
    log_path, when="midnight", backupCount=0, encoding="utf-8"
)
log_handler.namer = lambda name: name + ".gz"
log_handler.rotator = _log_rotator
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.ERROR)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[log_handler, stdout_handler]
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
from api_health import health
from notificador import Notificador
from bot_interactivo import BotInteractivo
from matriculas import AERONAVES_DATA, MATRICULA_TO_ICAO24

logger = logging.getLogger("AerobotMain")

async def tracker_staggered_task(tracker):
    logger.info("[SISTEMA] Hilo del Tracker Escalonado iniciado.")
    
    # Barrido rotativo de 8 zonas con ADSB.fi (dist=250 NM max permitido por la API).
    # ADSB.lol queda solo para militares (límite 500 pedidos/día) y OpenSky para la flota conocida.
    # Cobertura total de Argentina: lat -22 a -55, lon -53 a -73
    STEP_SECONDS = 11  # 8 pasos x 11s = 88s, dentro del ciclo de 90s
    MIL_CADA_CICLOS = 6  # ~9 min -> ~160 pedidos/día a ADSB.lol (/v2/mil)
    HEX_LOL_CADA_CICLOS = 6  # ~9 min -> ~160 pedidos/día a ADSB.lol (/v2/hex conocidos). Total ~320 de 500.
    zonas = [
        {"nombre": "NOA",             "lat": -24.0, "lon": -65.0, "dist": 250},  # Jujuy, Salta, Tucumán, Catamarca
        {"nombre": "NEA",             "lat": -28.0, "lon": -56.0, "dist": 250},  # Misiones, Corrientes, Formosa, Chaco
        {"nombre": "CENTRO",          "lat": -33.0, "lon": -63.0, "dist": 250},  # Córdoba, Santa Fe, Entre Ríos, San Luis
        {"nombre": "CUYO",            "lat": -34.0, "lon": -67.5, "dist": 250},  # Mendoza, San Juan, La Pampa
        {"nombre": "AMBA",            "lat": -35.0, "lon": -58.5, "dist": 250},  # AMBA, La Plata, Rosario, costa atlántica (antes lo cubría el cono de ADSB.fi)
        {"nombre": "PATAGONIA NORTE", "lat": -41.0, "lon": -68.0, "dist": 250},  # Neuquén, Río Negro
        {"nombre": "PATAGONIA SUR",   "lat": -49.0, "lon": -69.0, "dist": 250},  # Santa Cruz, Chubut sur
        {"nombre": "TIERRA DEL FUEGO","lat": -54.5, "lon": -68.0, "dist": 250},  # Ushuaia, TdF, Atlántico Sur
    ]
    
    def _pausa(api):
        return " [EN PAUSA]" if health.esta_pausada(api) else ""

    iteration = 0
    while True:
        try:
            start_time = time.time()
            iteration += 1
            health.iniciar_ciclo(iteration)
            
            logger.info(f"=== INICIANDO BARRIDO GLOBAL N° {iteration} ===")
            
            # Obtener lista de aviones conocidos para búsquedas HEX
            flota = db.get_all_aeronaves(solo_activas=True)
            icao_list = [a['icao24'] for a in flota if a['icao24']]
            # Hex alternativos del ARG-01 (capturados por callsign ARG01) tambien se consultan en todo el mundo
            icao_list += [h for h in db.get_alt_hexes("ARG-01") if h not in icao_list]
            
            for i, zona in enumerate(zonas):
                step_start = time.time()
                
                # 1. Zona del paso con ADSB.fi
                ac_list = await tracker.fetch_adsb_fi(lat=zona['lat'], lon=zona['lon'], dist=zona['dist'])
                tot, ofis = await tracker.process_detected(ac_list)
                logger.info(f"[RADAR] Paso {i+1}/{len(zonas)}: ADSB.fi (ZONA:{zona['nombre']}) -> {tot} aviones ({len(ofis)} ofis){_pausa('ADSB.fi')}")
                
                # 2. Intercalamos las otras APIs
                if i == 2 and iteration % MIL_CADA_CICLOS == 1:
                    ac_list = await tracker.fetch_adsb_lol_mil()
                    tot, ofis = await tracker.process_detected(ac_list)
                    logger.info(f"[RADAR] Paso 3: + ADSB.lol (MIL) -> {tot} aviones ({len(ofis)} ofis){_pausa('ADSB.lol-MIL')}")
                
                elif i == 3:
                    ac_list_live = await tracker.fetch_airplanes_live_hex(icao_list)
                    if ac_list_live:
                        tot_live, ofis_live = await tracker.process_detected(ac_list_live)
                        logger.info(f"[RADAR] Paso 4: + Airplanes.live-HEX (CONOCIDOS) -> {tot_live} aviones ({len(ofis_live)} ofis)")
                    
                    ac_list_os = await tracker.fetch_opensky(icao24_list=icao_list)
                    if ac_list_os is not None:
                        tot_os, ofis_os = await tracker.process_detected(ac_list_os)
                        logger.info(f"[RADAR] Paso 4: + OpenSky (CONOCIDOS) -> {tot_os} aviones ({len(ofis_os)} ofis)")
                    elif health.esta_pausada("OpenSky"):
                        logger.info("[RADAR] Paso 4: + OpenSky (CONOCIDOS) -> [EN PAUSA]")

                elif i == 6 and iteration % HEX_LOL_CADA_CICLOS == 4:
                    # Segunda fuente mundial de conocidos (reemplaza Airplanes.live-HEX)
                    ac_list_lol = await tracker.fetch_adsb_lol_hex(icao_list)
                    tot_l, ofis_l = await tracker.process_detected(ac_list_lol)
                    logger.info(f"[RADAR] Paso 7: + ADSB.lol-HEX (CONOCIDOS) -> {tot_l} aviones ({len(ofis_l)} ofis){_pausa('ADSB.lol-HEX')}")
                
                # Esperamos hasta cumplir los segundos del paso actual
                elapsed_step = time.time() - step_start
                sleep_time = max(0, STEP_SECONDS - elapsed_step)
                await asyncio.sleep(sleep_time)
            
            health.cerrar_ciclo()
            
            # Purga cada 10 ciclos
            if iteration % 10 == 0:
                purged_smart = await tracker.check_ghost_landings()
                await tracker.avisar_vuelos_colgados(horas=8)
                count = db.purge_ghost_vuelos(horas=8)
                if count > 0 or purged_smart > 0: 
                    logger.info(f"[DB] Purgados {count} vuelos colgados y {purged_smart} aterrizajes inteligentes.")
                    
            # Mantenimiento profundo diario (aprox cada 1000 ciclos)
            if iteration % 1000 == 0:
                pos_borradas = db.purge_old_positions(days=15)
                cand_borradas = db.purge_old_candidatas(hours=72)
                err_borrados = db.purge_old_api_errores(days=90)
                logger.info(f"[DB-MANTENIMIENTO] Borradas {pos_borradas} posiciones antiguas del disco, {cand_borradas} candidatas expiradas y {err_borrados} errores de API de más de 90 días.")

            # Heartbeat cada 10 ciclos (~15 minutos)
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
                
        except Exception as e:
            logger.error(f"[MAIN] Error reporte: {e}")
            await asyncio.sleep(60)

async def db_sync_task():
    """Sincroniza la DB de RAM a disco cada 15 minutos como red de seguridad."""
    logger.info("[DB-SYNC] Tarea de sincronización periódica iniciada (cada 15 min).")
    while True:
        try:
            await asyncio.sleep(900)  # 15 minutos
            if USE_RAM_DB:
                logger.info("[DB-SYNC] Sincronizando Base de Datos de RAM a Disco...")
                db.backup_to_disk(DB_ORIGINAL)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[DB-SYNC] Error en sync periódico: {e}")
            await asyncio.sleep(60)

async def run_bot_and_tracker():
    logger.info("--- Iniciando ArwenAirTracker (Modo Híbrido Estabilizado) ---")
    db.seed_db(AERONAVES_DATA, MATRICULA_TO_ICAO24)
    
    notificador = Notificador()
    tracker = Tracker(notificador)
    health.set_notificador(notificador)
    bot = BotInteractivo()
    
    # Alerta de Inicio en Telegram
    await notificador.alertar_especial("🚀 <b>ARWEN AIR TRACKER ONLINE</b>\n\nEl sistema híbrido de rastreo ha comenzado a operar.\nModo: Rotación Cruzada (N/S)\nFuentes: ADSB.fi (zonas), ADSB.lol (militares), OpenSky (conocidos)")
    
    tasks = [
        asyncio.create_task(tracker_staggered_task(tracker)), 
        asyncio.create_task(bot.run_async()), 
        asyncio.create_task(hourly_status_task(tracker, notificador)),
        asyncio.create_task(db_sync_task())
    ]
    
    logger.info("[SISTEMA] Verificando credenciales de APIs...")
    opensky_status = await tracker.verify_auth()
    twitter_ok = await asyncio.to_thread(notificador.verify_auth)
    
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
    
    loop = asyncio.get_running_loop()
    def handle_sigterm():
        logger.info("[SISTEMA] Señal de apagado (SIGTERM/SIGINT) recibida. Cancelando tareas para apagado seguro...")
        for task in tasks:
            task.cancel()
            
    if os.name != 'nt':
        loop.add_signal_handler(signal.SIGTERM, handle_sigterm)
        loop.add_signal_handler(signal.SIGINT, handle_sigterm)
        
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("[SISTEMA] Parada solicitada. Apagando...")
    finally:
        try:
            await tracker.aclose()
        except Exception:
            pass
        logger.info("[SISTEMA] Bot apagado.")
        if USE_RAM_DB:
            logger.info("[SISTEMA] Sincronización FINAL de DB a Disco antes de salir (incluye apagados por señal SIGTERM/SIGINT)...")
            db.backup_to_disk(DB_ORIGINAL)

if __name__ == "__main__":
    if os.name != 'nt':
        # Auto-limpieza de otras instancias de este mismo bot en este directorio para evitar conflictos de Telegram o DB
        my_pid = os.getpid()
        my_cwd = os.path.dirname(os.path.abspath(__file__))
        viejos = []
        for pid_str in os.listdir('/proc'):
            if pid_str.isdigit():
                pid = int(pid_str)
                if pid == my_pid:
                    continue
                try:
                    with open(f'/proc/{pid}/cmdline', 'r') as f:
                        cmd = f.read()
                    if 'main.py' in cmd:
                        cwd = os.readlink(f'/proc/{pid}/cwd')
                        if os.path.abspath(cwd) == os.path.abspath(my_cwd):
                            viejos.append(pid)
                except Exception:
                    pass
        # Primero SIGTERM (la instancia vieja guarda su DB a disco), y SIGKILL solo si no cierra
        for pid in viejos:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for _ in range(20):
            if not any(os.path.exists(f'/proc/{pid}') for pid in viejos):
                break
            time.sleep(0.5)
        for pid in viejos:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        time.sleep(1.0) # Esperar a que se liberen sockets/puertos/recursos

    try:
        asyncio.run(run_bot_and_tracker())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        logger.critical(f"FATAL: {e}")
        sys.exit(1)
