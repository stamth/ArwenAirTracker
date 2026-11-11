import asyncio
import datetime
import logging
import time

import httpx
from db import db

logger = logging.getLogger(__name__)

# Las 3 fuentes activas del radar
APIS = ["ADSB.fi", "ADSB.lol-MIL", "ADSB.lol-HEX", "OpenSky"]

# Pausa con espera creciente: 5, 10, 20, 40 y como máximo 60 minutos
BACKOFF_INICIAL = 300
BACKOFF_MAX = 3600

# Timeouts / fallas de conexión sueltas se arreglan solas en el ciclo siguiente.
# Se pausa y se avisa recién después de 3 ciclos seguidos fallando
# (ADSB.fi hace 8 pedidos por ciclo, las otras 1).
PEDIDOS_POR_CICLO = {"ADSB.fi": 8, "ADSB.lol-MIL": 1, "ADSB.lol-HEX": 1, "OpenSky": 1}
CICLOS_FALLANDO_PARA_AVISAR = 3

# Qué significa cada tipo de error (se usa en avisos y en /errores)
EXPLICACIONES = {
    "429": "Se pasó del límite de pedidos o créditos de la API.",
    "401": "Credenciales o token inválidos o vencidos.",
    "403": "Acceso denegado: sin permiso, API restringida o IP bloqueada.",
    "5xx": "Falla en el servidor de la API (es problema de ellos).",
    "TIMEOUT": "La API no respondió a tiempo (red del G450 o servidor lento o caído).",
    "CONEXION": "No se pudo conectar (sin internet, DNS o servidor caído).",
    "HTTP": "Respuesta HTTP inesperada de la API.",
    "OTRO": "Error inesperado al procesar la respuesta.",
}

TIPOS_INMEDIATOS = {"429", "401", "403", "5xx", "HTTP"}


def _hora(ts):
    return datetime.datetime.fromtimestamp(ts).strftime("%H:%M")


def _duracion(segundos):
    mins = int(segundos // 60)
    if mins < 1:
        return "menos de 1 min"
    if mins < 60:
        return f"{mins} min"
    return f"{mins // 60}h {mins % 60}min"


def clasificar_status(status_code):
    if status_code in (401, 403, 429):
        return str(status_code)
    if status_code >= 500:
        return "5xx"
    return "HTTP"


def clasificar_excepcion(e):
    if isinstance(e, httpx.TimeoutException):
        return "TIMEOUT"
    if isinstance(e, (httpx.ConnectError, httpx.NetworkError)):
        return "CONEXION"
    return "OTRO"


class ApiHealth:
    def __init__(self):
        self.notificador = None
        self._tareas = set()
        self.state = {api: self._estado_inicial() for api in APIS}
        self.ciclo_actual = None
        self.ultimo_ciclo = None

    def _estado_inicial(self):
        return {
            "pausada_hasta": 0,
            "backoff": BACKOFF_INICIAL,
            "fallas_seguidas": 0,
            "caida_desde": None,      # timestamp del primer error de la caída actual
            "caida_tipo": None,       # tipo de error con el que se avisó
            "ultimo_error": None,     # (ts, tipo, detalle)
            "ultimo_ok": None,
            "restantes": None,        # créditos / pedidos restantes si la API los informa
            "pedidos_hoy": 0,
            "dia": datetime.date.today(),
        }

    def set_notificador(self, notificador):
        self.notificador = notificador

    def _avisar(self, texto):
        if not self.notificador:
            return
        t = asyncio.create_task(self.notificador._send_owner(texto))
        self._tareas.add(t)
        t.add_done_callback(self._tareas.discard)

    # --- Estado ---

    def esta_pausada(self, api):
        return time.time() < self.state[api]["pausada_hasta"]

    def pausada_hasta(self, api):
        return self.state[api]["pausada_hasta"]

    def set_restantes(self, api, valor):
        self.state[api]["restantes"] = valor

    def pausa_preventiva(self, api, segundos, motivo):
        """Frena antes de llegar a cero cuando la API avisa que no quedan pedidos."""
        segundos = min(max(segundos, 1), BACKOFF_MAX)
        self.state[api]["pausada_hasta"] = time.time() + segundos
        if segundos >= 60:
            logger.info(f"[SALUD] {api}: pausa preventiva de {int(segundos)}s ({motivo}).")

    # --- Registro de resultados ---

    def ok(self, api, aviones=0):
        st = self.state[api]
        now = time.time()
        if st["caida_desde"] is not None and st["caida_tipo"] is not None:
            dur = _duracion(now - st["caida_desde"])
            logger.info(f"[SALUD] {api}: volvió a responder después de {dur}.")
            self._avisar(f"✅ <b>{api} volvió</b>\n\nEstuvo con problemas durante {dur}.")
        st.update({
            "pausada_hasta": 0, "backoff": BACKOFF_INICIAL, "fallas_seguidas": 0,
            "caida_desde": None, "caida_tipo": None, "ultimo_ok": now,
        })
        self._ciclo_sumar(api, ok=True, aviones=aviones)

    def error(self, api, tipo, detalle="", retry_after=None):
        st = self.state[api]
        now = time.time()
        detalle = str(detalle or "")
        st["ultimo_error"] = (now, tipo, detalle)
        st["fallas_seguidas"] += 1
        if st["caida_desde"] is None:
            st["caida_desde"] = now
        self._ciclo_sumar(api, ok=False, tipo=tipo)

        try:
            db.add_api_error(api, tipo, detalle[:300])
        except Exception as e:
            logger.error(f"[SALUD] No se pudo guardar el error en la DB: {e}")

        if tipo in TIPOS_INMEDIATOS:
            debe_pausar = True
        else:
            umbral = PEDIDOS_POR_CICLO.get(api, 1) * CICLOS_FALLANDO_PARA_AVISAR
            debe_pausar = st["fallas_seguidas"] >= umbral

        if not debe_pausar:
            logger.warning(f"[{api.upper()}] {tipo}: {detalle} (falla {st['fallas_seguidas']} seguida)")
            return

        # Si la API dice cuánto esperar se respeta, pero nunca más de 60 min
        if retry_after:
            espera = min(int(retry_after), BACKOFF_MAX)
        else:
            espera = st["backoff"]
        st["pausada_hasta"] = now + espera
        st["backoff"] = min(st["backoff"] * 2, BACKOFF_MAX)
        st["fallas_seguidas"] = 0

        vuelve = _hora(st["pausada_hasta"])
        logger.warning(f"[{api.upper()}] {tipo}: {detalle}. En pausa {espera // 60} min (vuelve a probar {vuelve}).")

        # Un aviso al empezar la caída o si cambia el tipo de error; los reintentos fallidos no avisan
        if st["caida_tipo"] != tipo:
            st["caida_tipo"] = tipo
            self._avisar(
                f"⚠️ <b>{api}: error {tipo}</b>\n\n"
                f"{EXPLICACIONES.get(tipo, '')}\n"
                f"<i>{detalle[:150]}</i>\n\n"
                f"Pausada {espera // 60} min, vuelve a probar a las {vuelve}."
            )

    # --- Ciclos (para /online) ---

    def iniciar_ciclo(self, numero):
        self.ciclo_actual = {
            "numero": numero, "inicio": time.time(),
            "apis": {api: {"pedidos": 0, "ok": 0, "aviones": 0, "errores": {}, "consultada": False} for api in APIS},
        }

    def _ciclo_sumar(self, api, ok, aviones=0, tipo=None):
        st = self.state[api]
        if st["dia"] != datetime.date.today():
            st["dia"] = datetime.date.today()
            st["pedidos_hoy"] = 0
        st["pedidos_hoy"] += 1
        if not self.ciclo_actual:
            return
        c = self.ciclo_actual["apis"][api]
        c["consultada"] = True
        c["pedidos"] += 1
        if ok:
            c["ok"] += 1
            c["aviones"] += aviones
        else:
            c["errores"][tipo] = c["errores"].get(tipo, 0) + 1

    def cerrar_ciclo(self):
        if not self.ciclo_actual:
            return
        self.ciclo_actual["fin"] = time.time()
        self.ultimo_ciclo = self.ciclo_actual
        self.ciclo_actual = None

    # --- Textos para el bot ---

    def texto_online(self):
        c = self.ultimo_ciclo
        if not c:
            return "⏳ Todavía no terminó el primer ciclo del radar. Probá en un par de minutos."
        msg = f"📡 <b>ESTADO DE LAS APIs</b>\n"
        msg += f"Último ciclo completo: N° {c['numero']} a las {_hora(c['fin'])} ({c['fin'] - c['inicio']:.0f}s)\n\n"
        for api in APIS:
            st = self.state[api]
            r = c["apis"][api]
            if self.esta_pausada(api):
                icono = "⏸️"
                linea = f"en pausa hasta las {_hora(st['pausada_hasta'])}"
                if st["ultimo_error"]:
                    linea += f" (último error: {st['ultimo_error'][1]})"
            elif not r["consultada"]:
                icono = "➖"
                linea = "no le tocaba en este ciclo"
                if st["ultimo_ok"]:
                    linea += f" (último OK {_hora(st['ultimo_ok'])})"
            elif r["ok"] == r["pedidos"]:
                icono = "✅"
                linea = f"{r['ok']}/{r['pedidos']} pedidos OK, {r['aviones']} aviones"
            elif r["ok"] > 0:
                icono = "⚠️"
                errs = ", ".join(f"{k} x{v}" for k, v in r["errores"].items())
                linea = f"{r['ok']}/{r['pedidos']} pedidos OK, {r['aviones']} aviones (errores: {errs})"
            else:
                icono = "❌"
                errs = ", ".join(f"{k} x{v}" for k, v in r["errores"].items())
                linea = f"0/{r['pedidos']} pedidos OK (errores: {errs})"
            msg += f"{icono} <b>{api}</b>: {linea}\n"
            if api == "OpenSky" and st["restantes"] is not None:
                msg += f"      Créditos restantes: {st['restantes']} de 4000\n"
            elif api in ("ADSB.lol-MIL", "ADSB.lol-HEX"):
                msg += f"      Pedidos hoy: {st['pedidos_hoy']} de 500 por día\n"
        return msg

    def texto_errores(self, dias=1):
        desde = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=dias)).isoformat()
        filas = db.get_api_errores_resumen(desde)
        periodo = "últimas 24 horas" if dias == 1 else f"últimos {dias} días"
        if not filas:
            return f"✅ Sin errores de conexión en las {periodo}."
        total = sum(f["cantidad"] for f in filas)
        msg = f"🧾 <b>ERRORES DE CONEXIÓN</b> ({periodo})\nTotal: <b>{total}</b>\n"
        api_actual = None
        tipos_vistos = []
        for f in filas:
            if f["api"] != api_actual:
                api_actual = f["api"]
                msg += f"\n<b>{api_actual}</b>\n"
            ultimo = datetime.datetime.fromisoformat(f["ultimo"]).astimezone().strftime("%d/%m %H:%M")
            msg += f"   • {f['tipo']}: {f['cantidad']} (último {ultimo})\n"
            if f["tipo"] not in tipos_vistos:
                tipos_vistos.append(f["tipo"])
        msg += "\n<b>Qué significa cada uno</b>\n"
        for t in tipos_vistos:
            msg += f"   • <b>{t}</b>: {EXPLICACIONES.get(t, '')}\n"
        return msg


health = ApiHealth()
