#!/bin/bash
# ============================================================
# Meeting Processor — launcher de duplo-clique (macOS/Linux)
# ============================================================
# Dê duplo clique neste arquivo no Finder. Ele:
#   1. compila a interface React (SPA) na primeira vez, se possível;
#   2. inicia o servidor local;
#   3. abre o navegador na aplicação;
#   4. mostra os logs. Feche esta janela (ou Ctrl-C) para parar.
#
# Não precisa de terminal nem de comandos — é só o duplo clique.

PORT=8765
URL="http://127.0.0.1:${PORT}/"

# Vai para a pasta do projeto (onde este script está), mesmo com espaços no caminho.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || { echo "Não consegui entrar em $DIR"; read -r -p "Enter para sair."; exit 1; }

PY="$DIR/.venv/bin/python"

# --- 1. Verifica o ambiente Python -------------------------------------------
if [ ! -x "$PY" ]; then
  echo "Ambiente virtual não encontrado em .venv/"
  echo "Crie uma vez com:"
  echo "    python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  read -r -p "Enter para sair."
  exit 1
fi

# --- 1b. Garante que as dependências estão instaladas ------------------------
# Usa python-docx (exportação Word) como sentinela: se faltar, sincroniza tudo.
if ! "$PY" -c "import docx" >/dev/null 2>&1; then
  echo "Instalando/atualizando dependências…"
  "$PY" -m pip install -q -r requirements.txt \
    || { echo "Falha ao instalar dependências (veja requirements.txt)."; read -r -p "Enter para sair."; exit 1; }
fi

# --- 2. Compila a SPA na primeira vez ou quando o código mudou ---------------
SPA_INDEX="meeting_processor/web/spa/index.html"
needs_build=false
if [ ! -f "$SPA_INDEX" ]; then
  needs_build=true
elif [ -n "$(find frontend/src frontend/index.html frontend/package.json -newer "$SPA_INDEX" 2>/dev/null)" ]; then
  needs_build=true   # fonte mais nova que o build → recompila
fi
if [ "$needs_build" = true ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "Compilando a interface (primeira vez ou após atualização)…"
    ( cd frontend && { [ -d node_modules ] || npm install; } && npm run build ) \
      || echo "Falha ao compilar a SPA — usando a interface clássica (HTMX)."
  else
    echo "Node/npm não encontrado — usando a interface clássica (HTMX)."
  fi
fi

# --- 3. Sobe o servidor (ou reaproveita um já rodando) ------------------------
SERVER_PID=""
if curl -s -o /dev/null --max-time 2 "$URL" 2>/dev/null; then
  echo "Servidor já está rodando em $URL"
else
  echo "Iniciando o Meeting Processor…"
  "$PY" -m meeting_processor web --port "$PORT" &
  SERVER_PID=$!
  # Para o servidor quando esta janela/script terminar.
  trap '[ -n "$SERVER_PID" ] && kill "$SERVER_PID" 2>/dev/null' EXIT INT TERM
fi

# --- 4. Espera a porta responder e abre o navegador --------------------------
for _ in $(seq 1 40); do
  curl -s -o /dev/null --max-time 2 "$URL" 2>/dev/null && break
  sleep 0.5
done

if command -v open >/dev/null 2>&1; then
  open "$URL"          # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL"      # Linux
fi

echo ""
echo "  Meeting Processor rodando em: $URL"
echo "  Feche esta janela ou pressione Ctrl-C para parar."
echo ""

# --- 5. Mantém o script vivo enquanto o servidor roda ------------------------
if [ -n "$SERVER_PID" ]; then
  wait "$SERVER_PID"
else
  # O servidor já existia: não foi iniciado por nós, então não o derrubamos.
  echo "(Servidor iniciado por outra janela; esta apenas abriu o navegador.)"
  read -r -p "Enter para fechar esta janela."
fi
