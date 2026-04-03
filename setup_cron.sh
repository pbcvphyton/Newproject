#!/bin/bash
# ============================================================
# JurisIntel — Setup do Cron para o Bot Evolutivo
# Configura o bot para rodar toda noite das 22h às 06h
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$SCRIPT_DIR/venv/bin/python"
BOT="$SCRIPT_DIR/bot_evolutivo.py"
LOG="$SCRIPT_DIR/logs/cron_bot.log"

if [ ! -f "$PYTHON" ]; then
    echo "❌ Virtual environment não encontrado."
    echo "   Execute primeiro:"
    echo "   cd $SCRIPT_DIR"
    echo "   python -m venv venv"
    echo "   source venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

mkdir -p "$SCRIPT_DIR/logs"

CRON_LINE="0 22 * * * cd $SCRIPT_DIR && $PYTHON $BOT --daemon --horas 8 >> $LOG 2>&1"

echo "╔══════════════════════════════════════════════════╗"
echo "║    🤖 JurisIntel — Setup do Bot Noturno         ║"
echo "╠══════════════════════════════════════════════════╣"
echo "║  Roda toda noite às 22:00 por 8h (até 06:00)   ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo "Linha do cron:"
echo "  $CRON_LINE"
echo ""

read -p "Adicionar ao crontab? (s/n): " CONFIRM

if [ "$CONFIRM" = "s" ] || [ "$CONFIRM" = "S" ]; then
    (crontab -l 2>/dev/null | grep -v "bot_evolutivo.py"; echo "$CRON_LINE") | crontab -
    echo ""
    echo "✅ Cron configurado!"
    echo "   Verificar: crontab -l"
    echo "   Remover:   crontab -l | grep -v bot_evolutivo | crontab -"
else
    echo "Cancelado. Para configurar manualmente: crontab -e"
fi

echo ""
echo "── ANTES DO PRIMEIRO USO ────────────────────────────"
echo "  cd $SCRIPT_DIR"
echo "  source venv/bin/activate"
echo "  python bot_evolutivo.py --semear"
echo "  python bot_evolutivo.py --ciclo    # teste manual"
echo "────────────────────────────────────────────────────"
