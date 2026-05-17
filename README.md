# 📡 Aerobot — ArwenAirTracker

[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

An advanced, hybrid, multi-source flight tracking bot designed to autonomously monitor and report the operations of the Argentine governmental and official state fleet in real time. It broadcasts notifications to Telegram and publishes summaries on Twitter/X.

---

## 🇪🇸 Español

### 🌟 Características Principales

*   **Rastreo Híbrido Multifuente**: Combina en tiempo real 4 APIs diferentes para máxima precisión de cobertura territorial:
    *   **Airplanes.live** (Barrido geográfico rotativo por zonas).
    *   **ADSB.fi** (Conos de alta densidad).
    *   **ADSB.lol** (Detección especializada en aeronaves militares).
    *   **OpenSky Network** (Seguimiento prioritario por códigos HEX e históricos).
*   **Filtro Inteligente de Aterrizaje**: Cuenta con una "sala de espera" temporal de 3 minutos para confirmación de aterrizajes, previniendo alertas falsas causadas por toques y despegues (*Touch-and-Go*), aproximaciones bajas o go-arounds típicos de vuelos de entrenamiento militar.
*   **Notificaciones Avanzadas en Telegram**:
    *   **Despegues**: Indica matrícula, modelo de avión, aeropuerto de origen exacto o estimado y la fuente API que captó el evento.
    *   **Seguimientos Activos**: Reporte horario automático con la lista de aeronaves que se encuentran actualmente volando en el espacio aéreo.
    *   **Aterrizajes**: Informa origen, destino, duración de vuelo, distancia recorrida en km, estimación de consumo de combustible, huella de CO₂ generada y el costo operativo estimado en dólares (USD).
*   **Integración con Twitter/X**: Publicación automática de resúmenes de vuelos realizados por aeronaves oficiales.
*   **Cazador Inteligente (Smart Hunter)**: Rastreador de aeronaves no identificadas.
    *   **Ventana de 72 horas**: Conserva las detecciones "huérfanas" por 3 días para su revisión.
    *   **Merge Automático**: Capacidad de unificar el código HEX detectado con el de una aeronave ya existente en la base de datos mediante `/reclutar <existente> + <candidata>`.
    *   **Lista Negra Permanente**: Descarte definitivo de aeronaves no deseadas con `/ignorar`.
*   **Seguridad y Anti-Spam Avanzados**:
    *   **Control de Acceso (RBAC)**: Comandos de administración y administración exclusivos para el Owner (invisible para los demás).
    *   **Baneo Silencioso Dinámico**: Escudo Anti-DDoS que ignora silenciosamente a los usuarios no autorizados después de su primera advertencia.
    *   **Sanitización de Entradas (Whitelist Regex)**: Protección total contra inyecciones SQL y ejecución de scripts bloqueando cualquier carácter que no sea alfanumérico a nivel núcleo.
*   **Bot Telegram Interactivo**: Interfaz integrada con comandos como `/help`, `/aviones` (lista de flota), `/seguimiento` (estado actual en vivo) y `/ayer` (resumen de vuelos del día anterior).
*   **Resiliencia**: Auto-limpieza de procesos colgados y liberación agresiva de puertos/bases de datos en cada inicio.

---

### 🚀 Instalación y Configuración

#### 1. Clonar el repositorio y preparar entorno
```bash
git clone https://github.com/tu-usuario/aerobot.git
cd aerobot
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configurar variables de entorno
Crea un archivo `.env` en la raíz del proyecto tomando como base el archivo `.env.example`:
```bash
cp .env.example .env
```
Edita `.env` con tus credenciales reales:
*   `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`.
*   `OPENSKY_CLIENT_ID` y `OPENSKY_CLIENT_SECRET`.
*   Llaves de API de Twitter (Consumer y Access Tokens) para el autopost.

#### 3. Inicializar y Correr el Bot
```bash
# Iniciar el rastreador e interactivo en segundo plano
python main.py run
```

---

## 🇬🇧 English

### 🌟 Key Features

*   **Multi-Source Hybrid Tracking**: Combines 4 different APIs in real time to ensure maximum coverage over the Argentine airspace:
    *   **Airplanes.live** (Dynamic geographical sweeps by sectors).
    *   **ADSB.fi** (High-precision local cones).
    *   **ADSB.lol** (Military aviation specialized feeds).
    *   **OpenSky Network** (Priority tracking via HEX codes).
*   **Smart Landing Confirmation**: Features a 3-minute "waiting room" buffer for landing states. It effectively filters out false landing alerts triggered by *Touch-and-Go* maneuvers, low approaches, or training patterns common in military bases.
*   **Rich Telegram Notifications**:
    *   **Takeoffs**: Reports registration, aircraft model, departure airport, and the API source that detected it.
    *   **Active Flights**: Automatic hourly summary listing all aircraft currently flying.
    *   **Landings**: Summarizes departure/destination, duration, distance, fuel burn, CO₂ footprint, and estimated flight cost (USD).
*   **Twitter/X Integration**: Automatic tweets summarizing completed state flights.
*   **Smart Hunter**: Scans and alerts on unidentified military or foreign government aircraft flying without a known official registration.
    *   **72-Hour Window**: Retains "orphan" detections for 3 days for administrative review.
    *   **Automatic Merge**: Ability to unify the detected HEX code with an existing aircraft in the database using `/reclutar <existing> + <candidate>`.
    *   **Permanent Blacklist**: Definitive discarding of unwanted aircraft with `/ignorar`.
*   **Advanced Cybersecurity & Anti-Spam**:
    *   **Role-Based Access Control (RBAC)**: Admin and management commands are strictly exclusive and only visible to the Owner.
    *   **Dynamic Silent Ban**: Anti-DDoS shield that silently ignores unauthorized users after their first warning.
    *   **Input Sanitization (Whitelist Regex)**: Bulletproof protection against SQL injections and malicious scripts by rigorously blocking non-alphanumeric characters.
*   **Interactive Telegram Bot**: Commands like `/help`, `/aviones` (fleet database), `/seguimiento` (live tracks), and `/ayer` (yesterday's flights summary).
*   **Resiliency**: Aggressive self-cleanup of stale background tasks and instant lock release of database/network ports on boot.

---

### 🚀 Setup and Installation

#### 1. Clone the repository and prepare environment
```bash
git clone https://github.com/your-username/aerobot.git
cd aerobot
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

#### 2. Configure Environment Variables
Create a `.env` file in the root folder using `.env.example` as a template:
```bash
cp .env.example .env
```
Fill `.env` with your real keys:
*   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
*   `OPENSKY_CLIENT_ID` and `OPENSKY_CLIENT_SECRET`.
*   Twitter/X developer keys for automated posting.

#### 3. Run the Bot
```bash
# Starts the background tracker and active bot
python main.py run
```

---

## 📄 License | Licencia
Distributed under the MIT License. See `LICENSE` for more information.

*Desarrollado para el monitoreo ético y transparente de la flota pública estatal.*
