#!/bin/bash

# =============================================
#  AEROBOT — Script de Arranque
# =============================================

BASE_DIR="/home/tomas/Bots/aerobot"
VENV_PYTHON="$BASE_DIR/venv/bin/python3"

cd "$BASE_DIR" || exit 1

echo "==========================================="
echo "  ✈️ AEROBOT"
echo "==========================================="

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ ERROR: No se encontró el entorno virtual en $VENV_PYTHON"
    exit 1
fi

echo "🔄 Verificando procesos anteriores..."
if pgrep -f "$BASE_DIR/venv/bin/python3 main.py" > /dev/null 2>&1; then
    echo "   ⚠️  Bot anterior detectado. Cerrándolo..."
    pkill -f "$BASE_DIR/venv/bin/python3 main.py"
    sleep 2
    if pgrep -f "$BASE_DIR/venv/bin/python3 main.py" > /dev/null 2>&1; then
        echo "   ⚠️  Quedan procesos. Forzando cierre..."
        pkill -9 -f "$BASE_DIR/venv/bin/python3 main.py"
        sleep 1
    fi
    echo "   ✅ Proceso anterior terminado."
fi

# Modo de ejecución
if [ "$1" == "--fg" ] || [ "$1" == "--foreground" ]; then
    echo "🖥️  Modo: FOREGROUND"
    exec "$VENV_PYTHON" main.py
else
    echo "💤 Modo: BACKGROUND"
    [ -f bot_run.log ] && mv -f bot_run.log bot_run.log.1
    nohup "$VENV_PYTHON" main.py > bot_run.log 2>&1 &
    sleep 2
    if pgrep -f "$BASE_DIR/venv/bin/python3 main.py" > /dev/null 2>&1; then
        echo "   ✅ Bot arrancado correctamente."
    else
        echo "   ❌ ERROR: El bot no pudo arrancar."
    fi
fi
