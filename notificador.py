import logging
import os
import asyncio
import datetime
import time
from telegram import Bot
from telegram.constants import ParseMode
from db import db

logger = logging.getLogger(__name__)

# Aviso privado al dueño cuando X no deja publicar (sin créditos, forbidden, etc.)
TWITTER_AVISO_INTERVALO = 24 * 3600  # como mucho un aviso por día

class Notificador:
    def __init__(self):
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
        self.twitter_enabled = os.environ.get("TWITTER_ENABLED") == "1"
        self.bot = Bot(token=self.bot_token) if self.bot_token else None
        self.owner_id = int(os.environ.get("AUTHORIZED_USER_ID", 0) or 0)
        self.last_alerts = {} # Para evitar spam
        self._init_twitter()

    def _init_twitter(self):
        if not self.twitter_enabled: return
        try:
            import tweepy
            # Usamos el Cliente v2 para compatibilidad con planes Basic/Pro
            self.twitter_client = tweepy.Client(
                consumer_key=os.environ.get("TWITTER_API_KEY"),
                consumer_secret=os.environ.get("TWITTER_API_SECRET"),
                access_token=os.environ.get("TWITTER_ACCESS_TOKEN"),
                access_token_secret=os.environ.get("TWITTER_ACCESS_SECRET")
            )
            logger.info("[TWITTER] Cliente API v2 inicializado correctamente.")
        except Exception as e:
            logger.error(f"[TWITTER] Error al inicializar v2: {e}")
            self.twitter_enabled = False

    def verify_auth(self):
        """Verifica las credenciales de Twitter al inicio"""
        if not self.twitter_enabled or getattr(self, "twitter_client", None) is None: return False
        try:
            me = self.twitter_client.get_me()
            if me and me.data: return True
        except Exception as e:
            logger.warning(f"[TWITTER] Falló la verificación de credenciales: {e}")
        return False

    async def _send_telegram(self, text):
        if not self.bot or not self.channel_id: return
        try:
            await self.bot.send_message(chat_id=self.channel_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            err_msg = str(e).lower()
            if "forbidden" in err_msg or "chat not found" in err_msg:
                logger.error(f"[TELEGRAM] Error permanente (403/404). Desactivando: {e}")
                self.bot = None
            else:
                logger.error(f"[TELEGRAM] Error al enviar: {e}")

    def _send_tweet(self, text):
        """
        Envía un tweet usando la API v2.
        Retorna None si no hubo intento (deshabilitado / fuera de whitelist),
        True si se publicó, o el mensaje de error (str) si X lo rechazó.
        """
        if not self.twitter_enabled: return None
        try:
            # Chequear whitelist de Twitter
            wl = db.get_setting("twitter_whitelist", "")
            if wl:
                # Si hay whitelist, verificar que la matrícula está en ella
                # El texto del tweet debe contener alguna matrícula de la whitelist
                mats = [m.strip() for m in wl.split(",") if m.strip()]
                if mats and not any(m in text for m in mats):
                    logger.info(f"[TWITTER] Matrícula no está en whitelist, omitiendo tweet.")
                    return None

            # v2 usa create_tweet y el límite es 280 caracteres
            tweet_text = (text[:277] + "...") if len(text) > 280 else text
            self.twitter_client.create_tweet(text=tweet_text)
            logger.info(f"[TWITTER] Tweet enviado con éxito.")
            return True
        except Exception as e:
            # No se desactiva Twitter: si faltan créditos, al recargarlos vuelve a publicar solo
            logger.error(f"[TWITTER] Error al enviar tweet (v2): {e}")
            status = getattr(getattr(e, "response", None), "status_code", None)
            return f"HTTP {status}: {e}" if status else str(e)

    async def _send_owner(self, text):
        """Mensaje privado al dueño del bot (no al canal público)."""
        if not self.bot or not self.owner_id: return
        try:
            await self.bot.send_message(chat_id=self.owner_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as e:
            logger.error(f"[TELEGRAM] Error al avisar al dueño: {e}")

    async def _reportar_resultado_tweet(self, resultado):
        """Avisa en privado si X no deja publicar (máx. 1 vez cada 24 h) y cuando se recupera."""
        if resultado is None:
            return
        if resultado is True:
            if db.get_setting("twitter_fallando", "0") == "1":
                db.set_setting("twitter_fallando", "0")
                db.set_setting("twitter_aviso_ts", "0")
                await self._send_owner("✅ <b>X volvió a publicar.</b> Los tweets salen de nuevo.")
            return
        db.set_setting("twitter_fallando", "1")
        ultimo_aviso = float(db.get_setting("twitter_aviso_ts", "0") or 0)
        if time.time() - ultimo_aviso < TWITTER_AVISO_INTERVALO:
            logger.info("[TWITTER] Falla ya avisada en las últimas 24 h. No se repite el aviso.")
            return
        db.set_setting("twitter_aviso_ts", str(time.time()))
        error = str(resultado).replace("<", "&lt;").replace(">", "&gt;")[:300]
        posible_creditos = any(k in error.lower() for k in ("402", "403", "forbidden", "credit", "payment", "usage"))
        msg = "⚠️ <b>X no deja publicar</b>\n\n"
        if posible_creditos:
            msg += "Probablemente se quedó <b>sin créditos</b>. Los aterrizajes no se están tuiteando.\n\n"
        else:
            msg += "Los aterrizajes no se están tuiteando.\n\n"
        msg += f"Error: <code>{error}</code>\n\n"
        msg += "<i>Te vuelvo a avisar en 24 h si sigue fallando.</i>"
        await self._send_owner(msg)

    async def alertar_despegue(self, aeronave, origen_nombre, origen_ciudad, hora_utc, icao24="", source=""):
        mat = aeronave['matricula']
        if self._is_throttled(f"dep_{mat}", 300): return
        
        # Hora Argentina (UTC-3)
        hora_arg = hora_utc - datetime.timedelta(hours=3)
        
        msg = f"🛫 <b>DESPEGUE DETECTADO</b>\n\n"
        msg += f"Aeronave: <b>{aeronave['nombre']}</b> (<code>{mat}</code>)\n"
        msg += f"Origen: <b>{origen_nombre}</b>, {origen_ciudad}\n"
        msg += f"Hora: {hora_utc.strftime('%H:%M')} UTC ({hora_arg.strftime('%H:%M')} ARG)\n"
        if icao24:
            msg += f"ICAO: <code>{icao24}</code>\n"
        if source:
            msg += f"Fuente: <i>{source}</i>"
        
        await self._send_telegram(msg)
        # NO tuitear despegues, solo aterrizajes

    async def alertar_aterrizaje(self, aeronave, v):
        mat = aeronave['matricula']
        dur = v['duracion_min']
        
        # Solo alertar si el vuelo duró más de 7 minutos (filtrar taxeos y falsos positivos)
        if dur < 7:
            logger.info(f"[NOTIF] Vuelo de {mat} ignorado por duración corta ({dur} min)")
            return
        
        # Hora de aterrizaje real (o la actual por defecto)
        try:
            dt_aterrizaje = datetime.datetime.fromisoformat(v.get('aterrizaje_utc', ''))
            if dt_aterrizaje.tzinfo is None: dt_aterrizaje = dt_aterrizaje.replace(tzinfo=datetime.timezone.utc)
            now_arg = dt_aterrizaje - datetime.timedelta(hours=3)
        except (ValueError, TypeError):
            now_arg = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
        
        # Formatear duración legible
        horas = dur // 60
        minutos = dur % 60
        dur_str = f"{horas}h {minutos}min" if horas > 0 else f"{minutos}min"
        
        msg = f"🛬 <b>ATERRIZAJE DETECTADO</b>\n\n"
        msg += f"Aeronave: <b>{aeronave['nombre']}</b> (<code>{mat}</code>)\n"
        msg += f"Desde: <b>{v['origen_nombre']}</b>, {v['origen_ciudad']}\n"
        msg += f"Hacia: <b>{v['destino_nombre']}</b>, {v['destino_ciudad']}\n"
        msg += f"⏱️ Duración: {dur_str}\n"
        modelo_avion = f"{aeronave.get('marca', '') or ''} {aeronave.get('modelo', '') or ''}".strip()
        if not modelo_avion:
            modelo_avion = "Modelo desconocido"
        msg += f"✈️ Modelo: <b>{modelo_avion}</b>\n"
        msg += f"ICAO: <code>{v.get('icao24', '?')}</code>\n"
        msg += f"🕒 {now_arg.strftime('%H:%M')} (ARG)"
        
        await self._send_telegram(msg)
        
        # Twitter: Solo si duró más de 15 minutos
        if self.twitter_enabled and dur >= 15:
            tweet = f"🛬 {aeronave['nombre']} ({mat}) aterrizó en {v['destino_nombre']} ({v['destino_ciudad']})\n"
            tweet += f"🛫 Desde: {v['origen_nombre']} ({v['origen_ciudad']})\n"
            tweet += f"⏱️ {dur_str}\n"
            tweet += f"✈️ {modelo_avion}\n"
            tweet += f"🕒 {now_arg.strftime('%H:%M')} (ARG)\n"
            tweet += f"#AvionesDeLEstado #Aerobot"
            resultado = await asyncio.to_thread(self._send_tweet, tweet)
            await self._reportar_resultado_tweet(resultado)

    async def alertar_desconocida(self, callsign, icao24, pais, source=None):
        if self._is_throttled(f"unknown_{icao24}", 3600): return
        msg = f"🕵️‍♂️ <b>CAZADOR: Aeronave No Identificada</b>\n\n"
        msg += f"Indicativo: <b>{callsign}</b>\n"
        msg += f"Código Hex: <code>{icao24}</code>\n"
        msg += f"Región: {pais}\n"
        if source:
            msg += f"API Origen: <code>{source}</code>\n"
        msg += f"\n<i>Posible aeronave gubernamental o militar nueva.</i>"
        await self._send_telegram(msg)

    async def alertar_especial(self, text, throttle_key=None):
        if throttle_key and self._is_throttled(throttle_key, 60): return
        await self._send_telegram(text)

    def _is_throttled(self, key, seconds):
        now = time.time()
        last = self.last_alerts.get(key, 0)
        if now - last < seconds:
            return True
        self.last_alerts[key] = now
        return False
