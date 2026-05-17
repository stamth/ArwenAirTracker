import logging
import os
import asyncio
import datetime
import time
from telegram import Bot
from telegram.constants import ParseMode
from db import db

logger = logging.getLogger(__name__)

class Notificador:
    def __init__(self):
        self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.channel_id = os.environ.get("TELEGRAM_CHANNEL_ID")
        self.twitter_enabled = os.environ.get("TWITTER_ENABLED") == "1"
        self.bot = Bot(token=self.bot_token) if self.bot_token else None
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
        except: pass
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
        """Envía un tweet usando la API v2."""
        if not self.twitter_enabled: return
        try:
            # Chequear whitelist de Twitter
            wl = db.get_setting("twitter_whitelist", "")
            if wl:
                # Si hay whitelist, verificar que la matrícula está en ella
                # El texto del tweet debe contener alguna matrícula de la whitelist
                mats = [m.strip() for m in wl.split(",") if m.strip()]
                if mats and not any(m in text for m in mats):
                    logger.info(f"[TWITTER] Matrícula no está en whitelist, omitiendo tweet.")
                    return

            # v2 usa create_tweet y el límite es 280 caracteres
            tweet_text = (text[:277] + "...") if len(text) > 280 else text
            self.twitter_client.create_tweet(text=tweet_text)
            logger.info(f"[TWITTER] Tweet enviado con éxito.")
        except Exception as e:
            logger.error(f"[TWITTER] Error al enviar tweet (v2): {e}")
            # Si es un error de permisos (403), desactivamos Twitter para no spamear errores
            if "forbidden" in str(e).lower():
                self.twitter_enabled = False

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
        msg += f"💵 Gasto est.: ${int(v['costo_usd']):,} USD\n"
        msg += f"ICAO: <code>{v.get('icao24', '?')}</code>\n"
        msg += f"🕒 {now_arg.strftime('%H:%M')} (ARG)"
        
        await self._send_telegram(msg)
        
        # Twitter: Solo si duró más de 15 minutos
        if self.twitter_enabled and dur >= 15:
            tweet = f"🛬 {aeronave['nombre']} ({mat}) aterrizó en {v['destino_nombre']} ({v['destino_ciudad']})\n"
            tweet += f"🛫 Desde: {v['origen_nombre']} ({v['origen_ciudad']})\n"
            tweet += f"⏱️ {dur_str}\n"
            tweet += f"💵 ~${int(v['costo_usd']):,} USD estimado\n"
            tweet += f"🕒 {now_arg.strftime('%H:%M')} (ARG)\n"
            tweet += f"#AvionesDeLEstado #Aerobot"
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_tweet, tweet)

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
