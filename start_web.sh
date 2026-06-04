#!/usr/bin/env bash
# ============================================================
# Meeting Processor - inicia o frontend local no navegador
# Equivalente Linux/macOS de start_web.bat
# ============================================================
set -e
cd "$(dirname "$0")"

echo "Iniciando frontend local em http://127.0.0.1:8765 ..."
echo "Pressione Ctrl+C para parar."

exec python3 -m meeting_processor web --port 8765
