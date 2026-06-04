# Frontend local

O Meeting Processor pode ser usado de duas formas, **simultaneamente** ou
separadas:

1. **Obsidian** — abra a pasta `vault/` como vault. As reuniões aparecem
   em `wiki/reunioes/`, com Kanban via plugin `obsidian-kanban`.
2. **Frontend local no navegador** — interface web servida pelo próprio
   app. Não precisa do Obsidian.

Ambos leem os mesmos arquivos do `vault/`. Use o que preferir.

---

## Subir o frontend local

```bash
python -m meeting_processor web
```

Padrão: <http://127.0.0.1:8765>.

### Opções

```bash
python -m meeting_processor web --host 0.0.0.0 --port 9000
python -m meeting_processor web --reload          # auto-reload (dev)
```

---

## O que ele oferece

- Lista de reuniões processadas, com data, duração e contagem de tarefas.
- Página de detalhe por reunião: resumo, tarefas (com checkbox visual)
  e transcrição completa colapsável.
- **Painel de controle no topo da home:**
  - Ligar / desligar / reiniciar o watcher (que monitora a pasta do OBS).
  - Alternar entre **Claude API** e **Ollama (local)** com um clique —
    a escolha é persistida no `.env` e, se o watcher estiver ativo, ele
    é reiniciado automaticamente para aplicar a nova preferência.
- Status do watcher e dos jobs em execução, atualizado a cada 5 s via
  HTMX (sem WebSocket).
- Página `/settings` com todos os parâmetros ativos.
- Formulário para disparar processamento manual de um arquivo de vídeo.
- API JSON: `/api/health`, `/api/meetings`, `/api/meetings/{id}`,
  `/api/watcher`, `/api/llm`.

### Como funciona o controle do watcher

O frontend gerencia o watcher como **subprocess filho do servidor web**.
Isso significa:

- Você pode subir o frontend e ligar o watcher pela UI — não precisa
  manter dois terminais abertos.
- Se o servidor web for encerrado (Ctrl+C ou shutdown), ele para o
  watcher também (via shutdown handler do FastAPI).
- O watcher escreve heartbeat em `vault/wiki/.watcher-heartbeat`. O
  frontend mostra "ativo" quando o subprocess está vivo **e** o
  heartbeat é recente (< 15 s).

### Como funciona o toggle de LLM

O endpoint `POST /actions/llm-provider` faz três coisas:

1. Atualiza `os.environ["MEETING_LLM_PROVIDER"]` no processo do servidor.
2. Atualiza `config.llm_provider` em memória (preservando comentários e
   outras variáveis do `.env`).
3. Reescreve a linha correspondente no `.env`.
4. Se o watcher subprocess estava rodando, faz `restart()` para que ele
   herde a nova variável de ambiente.

Próxima execução de pipeline (manual ou via watcher) já usa o novo
provedor.

---

## Stack

- **FastAPI** — servidor HTTP.
- **Jinja2** — templating server-side.
- **HTMX** (CDN) — refresh automático sem SPA/build.
- **Tailwind** (CDN) — estilo.

Sem `npm`, sem build step, sem Node.js. Toda a stack é Python puro.

---

## Rodar como serviço (Windows)

Para abrir o frontend toda vez que o computador ligar, use o Agendador
de Tarefas com a ação:

```
Programa: pythonw.exe
Argumentos: -m meeting_processor web
Diretório: C:\caminho\para\fast
```

Ou use NSSM para registrar como serviço Windows nativo.

---

## Acessar de outro dispositivo na rede local

```bash
python -m meeting_processor web --host 0.0.0.0
```

⚠️ Não há autenticação. Use só em rede confiável (sua casa) ou coloque
um reverse proxy (Caddy, nginx) com auth básica na frente.
