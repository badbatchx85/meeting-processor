#!/usr/bin/env bash
# ============================================================
# Meeting Processor - inicia watcher + servidor de controle
# Equivalente Linux/macOS de start_watcher.bat
# ============================================================
set -e
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[ERRO] ffmpeg nao encontrado no PATH."
    echo "Instale:  macOS 'brew install ffmpeg'  |  Linux 'sudo apt install ffmpeg'"
    exit 1
fi

exec python3 -m meeting_processor serve
