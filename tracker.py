import logging
import time
import datetime
import re
import os
import httpx
import asyncio
from geopy.distance import distance as geopy_distance
from geopy.geocoders import Nominatim
from db import db
from aeropuertos import AEROPUERTOS

logger = logging.getLogger(__name__)

TOURIST_DESTINATIONS = {"Bariloche", "Iguazú", "El Calafate", "Ushuaia", "Punta del Este"}
OFFICIAL_PREFIXES = ("LQ", "ARG", "PG", "GN", "AE", "PA")
COMMERCIAL_PREFIXES = ("LV", "LVL", "LVS", "AEA", "DSM", "IBE", "AAL", "UAL", "DAL", "AFR", "BAW", "DLH", "TAM", "GLO", "AZU", "CMP", "AVA", "BOV")

OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
OPENSKY_API_URL   = "https://opensky-network.org/api/states/all"

class OpenSkyTokenManager:
    """
    Maneja el token OAuth2 de OpenSky automáticamente.
    Los tokens duran 30 minutos. Esta clase los renueva solos.
    """
    def __init__(self):
        self.client_id     = os.environ.get("OPENSKY_CLIENT_ID", "")
        self.client_secret = os.environ.get("OPENSKY_CLIENT_SECRET", "")
        self._token        = None
        self._expires_at   = 0   # timestamp unix

    def is_configured(self):
        return bool(self.client_id and self.client_secret)

    async def get_token(self):
        """Retorna un token válido, renovándolo si expiró o está por expirar."""
        # Renovar si faltan menos de 60 segundos para expirar
        if self._token and time.time() < (self._expires_at - 60):
            return self._token
        return await self._refresh()

    async def _refresh(self):
        if not self.is_configured():
            return None
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    OPENSKY_TOKEN_URL,
                    data={
                        "grant_type":    "client_credentials",
                        "client_id":     self.client_id,
                        "client_secret": self.client_secret,
                    },
                    timeout=10.0
                )
                if r.status_code == 200:
                    data = r.json()
                    self._token      = data["access_token"]
                    expires_in       = data.get("expires_in", 1800)
                    self._expires_at = time.time() + expires_in
                    logger.info(f"[OPENSKY] Token OAuth2 renovado. Expira en {expires_in}s.")
                    return self._token
                elif r.status_code == 401:
                    logger.error("[OPENSKY] OAuth2: client_id o client_secret inválidos.")
                else:
                    logger.error(f"[OPENSKY] OAuth2: Error al obtener token ({r.status_code}): {r.text[:200]}")
        except Exception as e:
            logger.error(f"[OPENSKY] OAuth2: Excepción al renovar token: {e}")
        self._token = None
        return None

    async def headers(self):
        token = await self.get_token()
        if token:
            return {"Authorization": f"Bearer {token}", "User-Agent": "ArwenAirTracker/1.0"}
        return {"User-Agent": "ArwenAirTracker/1.0"}


class Tracker:
    def __init__(self, notificador):
        self.notificador = notificador
        self.last_hunter_alert = {}
        self.hourly_stats = {
            "Norte": {"total": set(), "gov": set()},
            "Sur": {"total": set(), "gov": set()}
        }
        self.opensky_tokens = OpenSkyTokenManager()
        self.opensky_blocked_until = 0
        self.geolocator = Nominatim(user_agent="ArwenAirTracker")
        self.pending_landings = {}  # {matricula: {"first_seen": timestamp, "ac": ac, "vuelo": vuelo_db, "a_db": a_db}}

    def _normalize_text(self, text):
        if not text: return ""
        return re.sub(r'[\s\-]', '', text).upper()

    # --- FETCHERS ---

    async def fetch_airplanes_live(self, lat=-35.0, lon=-64.0, dist=1500):
        """Usa Airplanes.live con punto y radio (más liviano)"""
        url = f"https://api.airplanes.live/v2/point/{lat}/{lon}/{dist}"
        headers = {"User-Agent": "ArwenAirTracker/1.0"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                r = await client.get(url, timeout=15.0)
                if r.status_code == 200:
                    data = r.json().get("ac") or []
                    return self._parse_adsb_exchange(data, bbox=None, source="Airplanes.live")
        except Exception as e:
            logger.error(f"[AIRPLANES.LIVE] Error: {e}")
        return []

    async def fetch_airplanes_live_hex(self, icao24_list):
        """Consulta Airplanes.live usando una sola petición con múltiples hex para evitar baneos."""
        if not icao24_list: return []
        # Filtramos vacíos y unimos con comas
        hex_string = ",".join([h.lower() for h in icao24_list if h])
        if not hex_string: return []
        
        url = f"https://api.airplanes.live/v2/hex/{hex_string}"
        headers = {"User-Agent": "ArwenAirTracker/1.0"}
        
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                r = await client.get(url, timeout=15.0)
                if r.status_code == 200:
                    data = r.json().get("ac") or []
                    return self._parse_adsb_exchange(data, bbox=None, source="Airplanes.live-HEX")
                elif r.status_code == 404:
                    # 404 significa que no encontró ninguno de esos aviones en el aire (comportamiento normal)
                    return []
                else:
                    logger.warning(f"[AIRPLANES.LIVE-HEX] HTTP {r.status_code}")
        except Exception as e:
            logger.error(f"[AIRPLANES.LIVE-HEX] Error: {e}")
        return []

    async def fetch_adsb_fi(self, lat=-35.0, lon=-64.0, dist=250):
        """Usa ADSB.fi con punto y radio (v3) - Max dist 250 NM"""
        # ADSB.fi v3 requiere lat/lon/dist en el path
        dist = min(dist, 250)
        url = f"https://opendata.adsb.fi/api/v3/lat/{lat}/lon/{lon}/dist/{dist}"
        headers = {"User-Agent": "ArwenAirTracker/1.0"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                r = await client.get(url, timeout=15.0)
                if r.status_code == 200:
                    data = r.json().get("ac") or []
                    return self._parse_adsb_exchange(data, bbox=None, source="ADSB.fi")
                else:
                    logger.warning(f"[ADSB.FI] Error {r.status_code} en {url}")
        except Exception as e:
            logger.error(f"[ADSB.FI] Error: {type(e).__name__} - {e}")
        return []

    async def fetch_adsb_lol(self, lat=-35.0, lon=-64.0, dist=250):
        """Usa ADSB.lol con punto y radio - Max dist 250 NM"""
        dist = min(dist, 250)
        url = f"https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{dist}"
        headers = {"User-Agent": "ArwenAirTracker/1.0"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                r = await client.get(url, timeout=15.0)
                if r.status_code == 200:
                    data = r.json().get("ac") or []
                    return self._parse_adsb_exchange(data, bbox=None, source="ADSB.lol")
                else:
                    logger.warning(f"[ADSB.LOL] Error {r.status_code} en {url}")
        except Exception as e:
            logger.error(f"[ADSB.LOL] Error: {type(e).__name__} - {e}")
        return []

    async def fetch_adsb_lol_mil(self):
        """Usa ADSB.lol para detectar exclusivamente aeronaves militares"""
        url = "https://api.adsb.lol/v2/mil"
        bbox_arg = (-56.0, -75.0, -22.0, -52.0) # Argentina Completa
        headers = {"User-Agent": "ArwenAirTracker/1.0"}
        try:
            async with httpx.AsyncClient(headers=headers) as client:
                r = await client.get(url, timeout=15.0)
                if r.status_code == 200:
                    data = r.json().get("ac") or []
                    return self._parse_adsb_exchange(data, bbox_arg, source="ADSB.lol-MIL")
                else:
                    logger.warning(f"[ADSB.LOL-MIL] Error {r.status_code} en {url}")
        except Exception as e:
            logger.error(f"[ADSB.LOL-MIL] Error: {type(e).__name__} - {e}")
        return []

    async def fetch_opensky(self, icao24_list=None):
        """
        Consulta OpenSky con OAuth2 para aeronaves conocidas.
        - Respeta cooldown de 15 min si recibe 429
        """
        if not icao24_list:
            return []

        # Verificar cooldown
        if time.time() < self.opensky_blocked_until:
            return None

        # Verificar si OAuth2 está configurado
        if not self.opensky_tokens.is_configured():
            return None

        # Filtrar icao24s válidos
        icao_validos = [i.lower() for i in icao24_list if i and len(i) == 6 and not i.lower().startswith("e0000")]
        if not icao_validos:
            return None

        params = [("icao24", icao) for icao in icao_validos]

        try:
            headers = await self.opensky_tokens.headers()
            async with httpx.AsyncClient() as client:
                r = await client.get(OPENSKY_API_URL, params=params, headers=headers, timeout=20.0)
                
                # Mostrar créditos restantes si están disponibles
                remaining_credits = r.headers.get("X-Rate-Limit-Remaining")
                if remaining_credits:
                    logger.info(f"[OPENSKY] ✅ Respuesta OK. Créditos restantes: {remaining_credits}")

                if r.status_code == 200:
                    states = r.json().get("states") or []
                    return self._parse_opensky(states)

                elif r.status_code == 401:
                    logger.warning("[OPENSKY] 401: Token expirado o inválido. Forzando renovación.")
                    self.opensky_tokens._token = None
                    self.opensky_tokens._expires_at = 0
                    return None

                elif r.status_code == 429:
                    retry_after = int(r.headers.get("X-Rate-Limit-Retry-After-Seconds", 900))
                    self.opensky_blocked_until = time.time() + retry_after
                    logger.warning(f"[OPENSKY] 429: Límite de créditos. Cooldown de {retry_after}s activado.")
                    return None

                elif r.status_code == 403:
                    logger.error("[OPENSKY] 403: Acceso denegado. Verificar permisos del API client.")
                    self.opensky_blocked_until = time.time() + 3600
                    return None

                else:
                    logger.warning(f"[OPENSKY] HTTP {r.status_code}")
                    return None

        except Exception as e:
            logger.error(f"[OPENSKY] Error: {e}")
            return None

    async def verify_auth(self):
        """
        Verifica las credenciales de OpenSky al inicio del bot.
        """
        if not self.opensky_tokens.is_configured():
            return "MISSING"

        token = await self.opensky_tokens.get_token()
        if not token:
            return "INVALID"

        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    OPENSKY_API_URL,
                    params=[("icao24", "e14d34")],  # ARG-03
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "ArwenAirTracker/1.0"},
                    timeout=10.0
                )
                if r.status_code == 200:
                    credits_left = r.headers.get("X-Rate-Limit-Remaining", "?")
                    logger.info(f"[OPENSKY] Auth OK. Créditos disponibles: {credits_left}")
                    return "OK"
                if r.status_code == 401:
                    return "INVALID"
                if r.status_code == 429:
                    return "RATE_LIMIT"
                return f"HTTP_{r.status_code}"
        except Exception as e:
            logger.error(f"[OPENSKY] verify_auth error: {e}")
            return "ERROR"


    # --- PARSERS (NORMALIZADORES) ---

    def _parse_adsb_exchange(self, ac_list, bbox, source):
        normalized = []
        for ac in ac_list:
            lat = ac.get("lat")
            lon = ac.get("lon")
            if lat is None or lon is None: continue
            
            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue
            
            # Filtro Geográfico local
            if bbox:
                if not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
                    continue
            
            alt_raw = ac.get("alt_baro")
            on_ground = False
            if str(alt_raw).lower() == "ground":
                alt = 0.0
                on_ground = True
            else:
                try: alt = float(alt_raw) if alt_raw is not None else 0.0
                except (ValueError, TypeError): alt = 0.0
            
            gs_raw = ac.get("gs")
            try: gs = float(gs_raw) if gs_raw is not None else 0.0
            except (ValueError, TypeError): gs = 0.0
            
            # Solo asumir en tierra si alt < 200 y gs < 50, o si lo dice explicitamente
            if not on_ground and alt < 200 and gs < 50:
                on_ground = True

            normalized.append({
                "hex": str(ac.get("hex", "")).lower(),
                "reg": str(ac.get("r", "")).strip().upper(),
                "callsign": str(ac.get("flight", "")).strip().upper(),
                "lat": lat, "lon": lon,
                "alt": alt,
                "on_ground": on_ground,
                "vel_kmh": gs * 1.852, # nudos a kmh
                "source": source
            })
        return normalized

    def _parse_opensky(self, states):
        normalized = []
        for s in states:
            lat, lon = s[6], s[5]
            if lat is None or lon is None: continue
            
            try:
                lat = float(lat)
                lon = float(lon)
            except (ValueError, TypeError):
                continue
                
            alt_raw = s[7]
            try: alt = float(alt_raw) if alt_raw is not None else 0.0
            except (ValueError, TypeError): alt = 0.0
            
            vel_raw = s[9]
            try: vel = float(vel_raw) if vel_raw is not None else 0.0
            except (ValueError, TypeError): vel = 0.0

            normalized.append({
                "hex": str(s[0]).lower(),
                "reg": "", # OpenSky no suele dar matricula en este endpoint
                "callsign": str(s[1] or "").strip().upper(),
                "lat": lat, "lon": lon,
                "alt": alt,
                "on_ground": bool(s[8]),
                "vel_kmh": vel * 3.6,
                "source": "OpenSky"
            })
        return normalized

    # --- LOGICA DE PROCESAMIENTO ---

    async def process_detected(self, aircraft_list, scan_mode="known"):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_str = now_utc.isoformat()
        
        flota_db = db.get_all_aeronaves(solo_activas=True)
        watchlist_hex = {a['icao24'].lower(): a for a in flota_db if a['icao24']}
        watchlist_reg = {self._normalize_text(a['matricula']): a for a in flota_db}
        # Mapa adicional por nombre (para matchear callsigns como "Cruz Del Sur")
        watchlist_call = {self._normalize_text(a['nombre']): a for a in flota_db if a.get('nombre')}
        
        count_total = len(aircraft_list)
        oficiales_nombres = []
        
        for ac in aircraft_list:
            icao24 = ac.get('hex', '')
            callsign = ac.get('callsign', '')
            reg = ac.get('reg', '')
            lat, lon = ac.get('lat'), ac.get('lon')
            
            if lat is None or lon is None:
                continue
                
            zona = "Norte" if lat > -35.0 else "Sur"
            
            # 1. ¿Es una aeronave conocida? (Por HEX, Registro o Callsign)
            a_db = watchlist_hex.get(icao24) or \
                   watchlist_reg.get(self._normalize_text(reg)) or \
                   watchlist_call.get(self._normalize_text(callsign))
            
            if a_db:
                mat = a_db['matricula']
                oficiales_nombres.append(mat)
                self.hourly_stats[zona]["gov"].add(icao24)
                self.hourly_stats[zona]["total"].add(icao24)
                
                # AUTO-UPDATE: Si lo detectamos por registro/callsign pero su ICAO24 cambió o faltaba, actualizar
                db_icao = (a_db.get('icao24') or '').lower()
                if icao24 and icao24 != db_icao:
                    logger.info(f"[ICAO-UPDATE] {mat}: ICAO24 actualizado de '{db_icao}' a '{icao24}'")
                    db.set_setting(f"icao_{mat}", icao24)  # Log del cambio
                    with db.connection_scope() as conn:
                        cursor = db.get_cursor(conn)
                        cursor.execute(
                            "UPDATE aeronaves SET icao24 = ? WHERE matricula = ?" if not db.is_postgres else "UPDATE aeronaves SET icao24 = %s WHERE matricula = %s",
                            (icao24, mat)
                        )
                
                # Lógica de vuelo (Despegue / Aterrizaje)
                await self._handle_flight_logic(a_db, ac, now_utc, now_str)
            
            else:
                # 2. No es conocida -> ¿Es un hallazgo del CAZADOR?
                self.hourly_stats[zona]["total"].add(icao24)
                
                # Si viene de ADSB.lol-MIL o tiene prefijo oficial
                es_mil = ac['source'] == "ADSB.lol-MIL"
                tiene_prefijo = (callsign and callsign.startswith(OFFICIAL_PREFIXES)) or (reg and reg.startswith(OFFICIAL_PREFIXES))
                es_comercial = (callsign and callsign.startswith(COMMERCIAL_PREFIXES)) or (reg and reg.startswith(COMMERCIAL_PREFIXES))
                
                if (es_mil or tiene_prefijo) and not es_comercial:
                    # Alertar si no es un vuelo comercial común (ej. ARG1234 de Aerolineas)
                    if not (callsign and callsign.startswith("ARG") and re.match(r"^ARG\d{4}$", callsign)):
                        if db.save_aeronave_candidata(callsign or reg or icao24, icao24, "Argentina", now_str):
                            label = "MILITAR" if es_mil else "GUBERNAMENTAL"
                            await self.notificador.alertar_desconocida(callsign or reg or icao24, icao24, f"Argentina ({label})", source=ac.get('source'))

        await self.check_pending_landings()
        return count_total, oficiales_nombres

    async def _handle_flight_logic(self, a_db, ac, now_utc, now_str):
        matricula = a_db['matricula']
        icao24 = ac['hex']
        lat, lon = ac['lat'], ac['lon']
        en_vuelo = not ac['on_ground']
        
        vuelo = db.get_vuelo_activo(matricula)
        
        if en_vuelo and not vuelo:
            near_icao, _ = self.find_nearest_airport(lat, lon)
            orig = AEROPUERTOS.get(near_icao, {"nombre": "Desconocido", "ciudad": "Local"})
            db.add_vuelo_activo(matricula, icao24, near_icao, orig['nombre'], orig['ciudad'], now_str, lat, lon, ac['alt'])
            await self.notificador.alertar_despegue(a_db, orig['nombre'], orig['ciudad'], now_utc, icao24=icao24, source=ac['source'])
        
        elif en_vuelo and vuelo:
            if matricula in self.pending_landings:
                del self.pending_landings[matricula]
                logger.info(f"[TRACKER] Aterrizaje PENDIENTE CANCELADO para {matricula} (volvió a subir/volar - Touch-and-Go).")
                
            alt_actual = ac['alt']
            alt_previa = vuelo.get('last_alt') or 0
            
            # PREVENCIÓN BUG: Ignorar caídas a 0 pies de la API si venía alto
            if alt_actual == 0 and alt_previa > 500:
                alt_actual = alt_previa
                
            # FILTRO INTELIGENTE: ¿Se movió significativamente?
            dist_mov = geopy_distance((vuelo['last_lat'], vuelo['last_lon']), (lat, lon)).km
            alt_diff = abs(alt_actual - alt_previa)
            
            # Actualizar siempre el estado "en vivo" en la tabla de activos
            db.update_vuelo_activo_posicion(matricula, lat, lon, alt_actual, now_str)
            
            # Solo guardar en el historial si el cambio es relevante (800m o 300ft)
            if dist_mov > 0.8 or alt_diff > 300:
                db.save_posicion(matricula, icao24, lat, lon, alt_actual, ac['vel_kmh'], 1, now_str)
            
        elif not en_vuelo and vuelo:
            # Filtro anti-spam para aterrizajes (evita touch-and-go y pérdida de señal en vuelo bajo)
            # Especialmente para helicópteros de patrullaje
            es_heli = "helicoptero" in (a_db.get('nombre') or "").lower() or \
                      any(k in (a_db.get('modelo') or "").lower() for k in ["bell", "eurocopter", "sikorsky", "h145", "as-350", "ec-145", "ec-135"])
            
            dt_despegue = datetime.datetime.fromisoformat(vuelo['despegue_utc'])
            if dt_despegue.tzinfo is None: dt_despegue = dt_despegue.replace(tzinfo=datetime.timezone.utc)
            dur_min = int((now_utc - dt_despegue).total_seconds() / 60)
            
            # Si es heli, mínimo 15 min para avisar aterrizaje. Si es avión, 5 min.
            min_vuelo = 15 if es_heli else 5
            if dur_min < min_vuelo:
                # Si no llegó al mínimo, no borramos el vuelo activo, lo dejamos que siga
                # Esto hace que si vuelve a subir, se considere el mismo vuelo.
                return
            
            if matricula not in self.pending_landings:
                self.pending_landings[matricula] = {
                    "first_seen": time.time(),
                    "a_db": a_db,
                    "ac": ac,
                    "vuelo": vuelo
                }
                logger.info(f"[TRACKER] Aterrizaje PENDIENTE detectado para {matricula}. Entrando a sala de espera (3 minutos)...")

    async def check_pending_landings(self):
        """Revisa la sala de espera de aterrizajes. Si llevan más de 180s en ella, confirma el aterrizaje."""
        now = time.time()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_str = now_utc.isoformat()
        
        to_trigger = []
        for mat, data in list(self.pending_landings.items()):
            if now - data["first_seen"] >= 180: # 3 minutos
                to_trigger.append(mat)
                
        for mat in to_trigger:
            data = self.pending_landings.pop(mat)
            a_db, ac, vuelo = data["a_db"], data["ac"], data["vuelo"]
            icao24 = ac['hex']
            lat, lon = ac['lat'], ac['lon']
            
            dt_despegue = datetime.datetime.fromisoformat(vuelo['despegue_utc'])
            if dt_despegue.tzinfo is None: dt_despegue = dt_despegue.replace(tzinfo=datetime.timezone.utc)
            dur_min = int((now_utc - dt_despegue).total_seconds() / 60)
            
            loc_name = await self.get_location_display(lat, lon)
            parts = loc_name.split(",")
            dest_n, dest_c = parts[0].strip(), (parts[1].strip() if len(parts) > 1 else parts[0].strip())
            near_icao, _ = self.find_nearest_airport(lat, lon)
            orig = AEROPUERTOS.get(vuelo['origen_icao'], {"nombre": "Desconocido", "ciudad": "Local", "pais": "Argentina"})
            dist_km = geopy_distance((vuelo['despegue_lat'], vuelo['despegue_lon']), (lat, lon)).km
            
            v_data = {
                "matricula": mat, "icao24": icao24, "callsign": ac['callsign'], "origen_icao": vuelo['origen_icao'],
                "origen_nombre": orig['nombre'], "origen_ciudad": orig['ciudad'], "origen_pais": orig.get('pais', 'Argentina'),
                "destino_icao": near_icao, "destino_nombre": dest_n, "destino_ciudad": dest_c, "destino_pais": AEROPUERTOS.get(near_icao, {}).get('pais', 'Argentina'),
                "despegue_utc": vuelo['despegue_utc'], "aterrizaje_utc": now_str, "duracion_min": dur_min,
                "distancia_km": dist_km, "costo_usd": (dur_min/60)*a_db['costo_hora_usd'],
                "consumo_fuel_l": (dur_min/60)*(a_db.get('litros_hora_estimado') or 0),
                "emisiones_co2_kg": (dur_min/60)*(a_db.get('co2_kg_hora_estimado') or 0),
                "es_internacional": 1 if orig.get('pais', 'Argentina') != AEROPUERTOS.get(near_icao, {}).get('pais', 'Argentina') else 0,
                "es_finde": 1 if dt_despegue.weekday() >= 5 else 0, "es_nocturno": 1 if dt_despegue.hour < 6 or dt_despegue.hour >= 23 else 0
            }
            
            try:
                db.save_vuelo(v_data)
                db.remove_vuelo_activo(mat)
                db.save_posicion(mat, icao24, lat, lon, ac['alt'], ac['vel_kmh'], 0, now_str)
                await self.notificador.alertar_aterrizaje(a_db, v_data)
                logger.info(f"[TRACKER] Aterrizaje CONFIRMADO y guardado en DB para {mat} tras cumplir espera en tierra.")
            except Exception as e:
                logger.error(f"[TRACKER] Error al guardar aterrizaje confirmado para {mat}: {e}")

    # --- UTILIDADES ---

    def find_nearest_airport(self, lat, lon):
        if not AEROPUERTOS: return "UNKNOWN", 9999
        min_dist, nearest = 9999, "UNKNOWN"
        for icao, data in AEROPUERTOS.items():
            a_lat, a_lon = data.get('lat'), data.get('lon')
            if a_lat is None or a_lon is None: continue
            d = geopy_distance((lat, lon), (a_lat, a_lon)).km
            if d < min_dist: min_dist, nearest = d, icao
        return nearest, min_dist

    async def get_location_display(self, lat, lon):
        icao, dist = self.find_nearest_airport(lat, lon)
        if dist < 15 and icao in AEROPUERTOS:
            a = AEROPUERTOS[icao]
            return f"{a['nombre']}, {a['ciudad']}"
        try:
            location = await asyncio.to_thread(self.geolocator.reverse, f"{lat}, {lon}", exactly_one=True, timeout=5)
            if location:
                addr = location.raw.get('address', {})
                city = addr.get('city') or addr.get('town') or addr.get('village') or addr.get('county') or "Area rural"
                state = addr.get('state', "Argentina")
                return f"{city}, {state}"
        except: pass
        return f"Posicion desconocida ({lat:.2f}, {lon:.2f})"

    async def check_ghost_landings(self):
        """Revisa vuelos colgados. Si están a <5km de un aeropuerto y bajo, asume que aterrizaron (30 min de espera)."""
        vuelos = db.get_vuelos_activos()
        count_purged = 0
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_str = now_utc.isoformat()
        
        for v in vuelos:
            last_ts = v.get('last_update')
            if not last_ts: continue
            
            try:
                dt_last = datetime.datetime.fromisoformat(last_ts)
                if dt_last.tzinfo is None: dt_last = dt_last.replace(tzinfo=datetime.timezone.utc)
                mins_offline = int((now_utc - dt_last).total_seconds() / 60)
                
                if mins_offline < 30: continue
                
                alt_raw = v.get('last_alt')
                if str(alt_raw).lower() == "ground":
                    alt = 0
                else:
                    try: alt = float(alt_raw) if alt_raw is not None else 0
                    except: alt = 0
                    
                if alt < 1500:
                    near_icao, dist_km = self.find_nearest_airport(v['last_lat'], v['last_lon'])
                    if dist_km < 5.0:
                        logger.info(f"[SMART-LANDING] {v['matricula']} dado por aterrizado en {near_icao} (Offline {mins_offline}m, Alt {alt}ft, Dist {dist_km:.1f}km)")
                        
                        dt_despegue = datetime.datetime.fromisoformat(v['despegue_utc'])
                        if dt_despegue.tzinfo is None: dt_despegue = dt_despegue.replace(tzinfo=datetime.timezone.utc)
                        dur_min = int((now_utc - dt_despegue).total_seconds() / 60)
                        
                        loc_name = await self.get_location_display(v['last_lat'], v['last_lon'])
                        parts = loc_name.split(",")
                        dest_n = parts[0].strip()
                        dest_c = parts[1].strip() if len(parts) > 1 else dest_n
                        
                        # Calculamos los datos completos para el vuelo fantasma
                        v_data = {
                            "matricula": v['matricula'], "icao24": v['icao24'], "callsign": v.get('callsign', ''), 
                            "origen_icao": v['origen_icao'],
                            "origen_nombre": v['origen_nombre'], "origen_ciudad": v['origen_ciudad'], "origen_pais": "Argentina",
                            "destino_icao": near_icao, "destino_nombre": dest_n, "destino_ciudad": dest_c, "destino_pais": AEROPUERTOS.get(near_icao, {}).get('pais', 'Argentina'),
                            "despegue_utc": v['despegue_utc'], "aterrizaje_utc": now_str, "duracion_min": dur_min,
                            "distancia_km": geopy_distance((v['despegue_lat'], v['despegue_lon']), (v['last_lat'], v['last_lon'])).km,
                            "costo_usd": 0, "consumo_fuel_l": 0, "emisiones_co2_kg": 0,
                            "es_internacional": 0, "es_finde": 0, "es_nocturno": 0
                        }
                        
                        a_db = db.get_all_aeronaves(solo_activas=False)
                        aero = next((x for x in a_db if x['matricula'] == v['matricula']), None)
                        if aero:
                            v_data["costo_usd"] = (dur_min/60)*aero['costo_hora_usd']
                            v_data["consumo_fuel_l"] = (dur_min/60)*(aero.get('litros_hora_estimado') or 0)
                            v_data["emisiones_co2_kg"] = (dur_min/60)*(aero.get('co2_kg_hora_estimado') or 0)
                            v_data["es_finde"] = 1 if dt_despegue.weekday() >= 5 else 0
                            v_data["es_nocturno"] = 1 if dt_despegue.hour < 6 or dt_despegue.hour >= 23 else 0

                        db.save_vuelo(v_data)
                        db.remove_vuelo_activo(v['matricula'])
                        
                        a_db = db.get_all_aeronaves(solo_activas=False)
                        aero = next((x for x in a_db if x['matricula'] == v['matricula']), None)
                        if aero:
                            from db import db as db_instance
                            with db_instance.connection_scope() as conn:
                                cursor = db_instance.get_cursor(conn)
                                v_data = cursor.execute("SELECT * FROM vuelos WHERE matricula=? ORDER BY aterrizaje_utc DESC LIMIT 1" if not db_instance.is_postgres else "SELECT * FROM vuelos WHERE matricula=%s ORDER BY aterrizaje_utc DESC LIMIT 1", (v['matricula'],)).fetchone()
                                if v_data and mins_offline < 90:
                                    await self.notificador.alertar_aterrizaje(aero, dict(v_data))
                        count_purged += 1
            except Exception as e:
                logger.error(f"[SMART-LANDING] Error procesando {v.get('matricula')}: {e}")
        return count_purged
