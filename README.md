# Meeting Processor

> Pipeline local que transforma gravações de reuniões (OBS / qualquer
> vídeo) em **transcrição**, **resumo executivo**, **tarefas extraídas**
> e **quadro Kanban** — usando Whisper local + LLM (Claude API ou
> Ollama local). Frontend opcional no navegador, ou abra como vault no
> Obsidian.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Visão geral

Quando você termina uma reunião gravada com o OBS, o sistema:

1. **Detecta** o novo arquivo de vídeo na pasta monitorada.
2. **Extrai o áudio** com `ffmpeg`.
3. **Transcreve** localmente via `whisper.cpp` (GPU/CPU) ou `openai-whisper`.
4. **Resume** com a LLM escolhida — Claude API (qualidade máxima) ou
   Ollama local (privacidade total, sem custo).
5. **Gera** uma pasta no `vault/` com:
   - nota principal (nó central no grafo do Obsidian),
   - resumo executivo + resumo por blocos de 5 minutos,
   - lista de tarefas com responsável/prazo/prioridade,
   - quadro Kanban,
   - transcrição completa com timestamps.
6. **Atualiza** o `index.md`, `log.md` e `hot.md` do vault wiki.

Você consome o resultado por **Obsidian** ou pelo **frontend web local**
embutido — ambos leem os mesmos arquivos.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Requisitos](#requisitos)
- [Instalação do zero](#instalação-do-zero)
- [Configuração](#configuração)
- [Uso](#uso)
- [Frontend: Obsidian ou navegador](#frontend-obsidian-ou-navegador)
- [Trocar entre Claude API e LLM local](#trocar-entre-claude-api-e-llm-local)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Testes](#testes)
- [Solução de problemas](#solução-de-problemas)
- [Roadmap / contribuições](#roadmap--contribuições)
- [Licença](#licença)

---

## Arquitetura

```
┌────────────┐   ffmpeg    ┌──────────────┐   whisper.cpp   ┌────────────┐
│  vídeo OBS │ ──────────▶│   áudio WAV  │ ──────────────▶│ transcrição │
└────────────┘             └──────────────┘                 └─────┬──────┘
                                                                  │
                                                       ┌──────────┴──────────┐
                                                       │  Summarizer (LLM)   │
                                                       │  ┌─ AnthropicSum.   │
                                                       │  └─ OllamaSum.      │
                                                       └──────────┬──────────┘
                                                                  ▼
        ┌──────────────────────────────────────────────────────────────────┐
        │  vault/wiki/reunioes/<pasta>/                                    │
        │   ├─ {pasta}.md           (nó central)                           │
        │   ├─ Resumo - *.md         (resumo executivo + por janelas)      │
        │   ├─ Tarefas - *.md        (Kanban)                              │
        │   └─ Transcricao - *.md    (texto bruto com timestamps)          │
        └──────────────────────────────────────────────────────────────────┘
                              │                          │
                              ▼                          ▼
                  ┌────────────────────┐      ┌────────────────────┐
                  │     Obsidian       │      │  Frontend local    │
                  │ (Kanban, gráfico)  │      │  (FastAPI + HTMX)  │
                  └────────────────────┘      └────────────────────┘
```

---

## Requisitos

- **Python 3.11+**
- **ffmpeg** (no PATH)
- **Sistema:** Windows 10/11, macOS ou Linux
- **Para Whisper GPU (opcional):** `whisper.cpp` com Vulkan/CUDA/Metal
  ou GPU com drivers configurados para `openai-whisper`
- **Para LLM local (opcional):** Ollama instalado
- **Para frontend Obsidian (opcional):** Obsidian instalado

---

## Instalação do zero

### 1. Clone o repositório

```bash
git clone https://github.com/SEU-USUARIO/meeting-processor.git
cd meeting-processor
```

### 2. Crie um ambiente virtual e instale dependências

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Instale o ffmpeg

| SO       | Comando                                    |
|----------|--------------------------------------------|
| Windows  | `winget install Gyan.FFmpeg`               |
| macOS    | `brew install ffmpeg`                      |
| Linux    | `sudo apt install ffmpeg` (Ubuntu/Debian)  |

Verifique:
```bash
ffmpeg -version
```

### 4. Configure o Whisper

Por padrão o pipeline usa `whisper.cpp` (mais rápido que `openai-whisper`).
Coloque os binários e modelo nestes caminhos:

```
.whisper-cpp/whisper-cli.exe        # binário do whisper.cpp
.models/ggml-large-v3-turbo.bin     # modelo GGML large
```

- Binário: <https://github.com/ggerganov/whisper.cpp/releases>
- Modelo: <https://huggingface.co/ggerganov/whisper.cpp/tree/main>
  → `ggml-large-v3-turbo.bin` (~1.5 GB).

Se preferir o `openai-whisper` puro Python (mais lento, sem build), edite
`meeting_processor/transcriber.py` para usar a lib `whisper` — está nas
dependências.

### 5. Escolha o provedor de LLM

**Opção A — Claude API (qualidade máxima):**

1. Crie uma API key em <https://console.anthropic.com/>.
2. Copie `.env.example` para `.env`.
3. Edite o `.env`:
   ```dotenv
   MEETING_LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=sk-ant-...
   ```

**Opção B — LLM local com Ollama (privacidade total, sem custo):**

1. Instale o Ollama: <https://ollama.com/download>
2. Baixe o modelo padrão:
   ```bash
   ollama pull qwen2.5:14b
   ```
3. No `.env`:
   ```dotenv
   MEETING_LLM_PROVIDER=local
   ```

Detalhes em [`docs/llm-local.md`](docs/llm-local.md).

### 6. Ajuste a pasta monitorada

Edite `config.yaml`:

```yaml
watch_dir: "C:\\Users\\SEU_USUARIO\\Videos\\OBS"
```

Ou via env var: `MEETING_WATCH_DIR=...` no `.env`.

### 7. Pronto — teste rápido

```bash
python -m meeting_processor process caminho/para/teste.mkv
```

---

## Configuração

A configuração é carregada em duas camadas:

1. **`config.yaml`** — valores default versionados.
2. **`.env`** — override por variável de ambiente (não versionado).

Variáveis de ambiente reconhecidas (todas opcionais):

| Variável                       | Mapeia para            | Exemplo                          |
|--------------------------------|------------------------|----------------------------------|
| `MEETING_LLM_PROVIDER`         | `llm_provider`         | `anthropic` \| `local`           |
| `ANTHROPIC_API_KEY`            | `anthropic_api_key`    | `sk-ant-...`                     |
| `MEETING_ANTHROPIC_MODEL`      | `anthropic_model`      | `claude-sonnet-4-20250514`       |
| `MEETING_OLLAMA_BASE_URL`      | `ollama_base_url`      | `http://localhost:11434`         |
| `MEETING_OLLAMA_MODEL`         | `ollama_model`         | `qwen2.5:14b`                    |
| `MEETING_OLLAMA_TEMPERATURE`   | `ollama_temperature`   | `0.2`                            |
| `MEETING_OLLAMA_NUM_CTX`       | `ollama_num_ctx`       | `16384`                          |
| `MEETING_OLLAMA_REQUEST_TIMEOUT` | `ollama_request_timeout` | `600`                       |
| `MEETING_WATCH_DIR`            | `watch_dir`            | `C:\Users\X\Videos\OBS`          |
| `MEETING_VAULT_DIR`            | `vault_dir`            | `./vault`                        |
| `MEETING_WHISPER_MODEL`        | `whisper_model`        | `large`                          |
| `MEETING_WHISPER_LANGUAGE`     | `whisper_language`     | `pt`                             |
| `MEETING_WHISPER_DEVICE`       | `whisper_device`       | `auto` \| `cpu` \| `cuda`        |
| `MEETING_LOG_LEVEL`            | `log_level`            | `DEBUG` \| `INFO` \| `WARNING`   |

---

## Uso

### Modos de execução

| Comando                                            | O que faz                                    |
|----------------------------------------------------|----------------------------------------------|
| `python -m meeting_processor watch`                | Monitora a pasta do OBS (modo padrão).       |
| `python -m meeting_processor serve`                | Watcher + servidor de controle HTTP.         |
| `python -m meeting_processor web`                  | Frontend local em <http://127.0.0.1:8765>.   |
| `python -m meeting_processor process <vídeo>`      | Processa um arquivo manualmente.             |

### Atalhos no Windows

- `start_watcher.bat` — inicia o watcher.
- `start_web.bat` — inicia o frontend.
- `start_watcher_silent.vbs` — watcher em background, sem janela.

### Fluxo típico

1. Grave a reunião no OBS — saída em `watch_dir`.
2. Watcher detecta o arquivo, espera estabilizar (10 s sem mudança), processa.
3. Acompanhe o progresso em **um destes**:
   - `vault/wiki/reunioes/Dashboard.md` no Obsidian (atualizado em tempo real),
   - <http://127.0.0.1:8765> se o frontend estiver rodando.
4. Resultado: nova pasta em `vault/wiki/reunioes/<data hora - nome>/`.

---

## Frontend: Obsidian ou navegador

Você pode usar **um dos dois**, **os dois**, ou **nenhum** (consumir os
arquivos `.md` direto). Eles compartilham o mesmo `vault/`.

### Opção 1 — Obsidian

Veja [`docs/obsidian.md`](docs/obsidian.md). Pontos altos:

- Plugin Kanban renderiza `Tarefas - *.md` como quadro arrastável.
- Plugin Calendar agrupa por data.
- Grafo do Obsidian liga a nota central da reunião → Resumo / Tarefas / Transcrição.
- Dashboard ao vivo em `wiki/reunioes/Dashboard.md`.

### Opção 2 — Frontend local (navegador)

Stack: **FastAPI + HTMX + Tailwind** (CDN, sem build).

```bash
python -m meeting_processor web
# abrir http://127.0.0.1:8765
```

Oferece:
- Lista de reuniões com data, duração e tarefas.
- Página de detalhe (resumo + tarefas + transcrição colapsável).
- **Botão para ligar/desligar/reiniciar o watcher** sem abrir terminal.
- **Toggle ao vivo entre Claude API e Ollama local** — persiste no `.env`
  e reinicia o watcher automaticamente para aplicar.
- Status do watcher e jobs ativos com refresh automático (5 s).
- Página de configuração mostrando provedor LLM ativo, modelo, caminhos.
- API JSON: `/api/health`, `/api/meetings`, `/api/meetings/{id}`,
  `/api/watcher`, `/api/llm`.

Detalhes em [`docs/frontend-local.md`](docs/frontend-local.md).

---

## Trocar entre Claude API e LLM local

Ambos os provedores produzem o mesmo `MeetingSummary`. A escolha é feita
exclusivamente por config — não há mudança de código.

```dotenv
# Claude API
MEETING_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Ollama local
MEETING_LLM_PROVIDER=local
```

Para alternar pontualmente sem editar o `.env`:

```powershell
# Windows PowerShell
$env:MEETING_LLM_PROVIDER = "local"
python -m meeting_processor process video.mkv
```

```bash
# macOS / Linux
MEETING_LLM_PROVIDER=local python -m meeting_processor process video.mkv
```

Comparativo rápido:

| Critério            | Claude API           | Ollama local (qwen2.5:14b) |
|---------------------|----------------------|----------------------------|
| Qualidade do resumo | ★★★★★              | ★★★★☆                     |
| Privacidade         | dados saem da máquina | dados não saem            |
| Custo / reunião     | ~US$0.05–0.30        | zero                       |
| Velocidade (1h reu) | ~10–20 s             | ~30–120 s (depende GPU)    |
| Setup               | API key              | instalar Ollama + modelo   |

Detalhes em [`docs/llm-local.md`](docs/llm-local.md).

---

## Estrutura do repositório

```
fast/
├── meeting_processor/
│   ├── __main__.py          # CLI (watch / serve / web / process)
│   ├── config.py            # Settings + load_config (YAML + env)
│   ├── audio.py             # Extração via ffmpeg
│   ├── transcriber.py       # Whisper (whisper.cpp / openai-whisper)
│   ├── summarizer.py        # AnthropicSummarizer + OllamaSummarizer + factory
│   ├── note_generator.py    # Geração de notas Markdown para Obsidian
│   ├── kanban.py            # Geração de quadros Kanban por reunião
│   ├── wiki_integrator.py   # Integração com index/log/hot do vault
│   ├── dashboard.py         # Dashboard ao vivo no Obsidian
│   ├── pipeline.py          # Orquestrador de todas as etapas
│   ├── watcher.py           # Watchdog na pasta do OBS
│   ├── control_server.py    # HTTP simples para start/stop do watcher
│   ├── models.py            # Modelos pydantic (Transcript, ActionItem...)
│   └── web/                 # Frontend local (FastAPI + HTMX + Tailwind)
│       ├── app.py
│       ├── templates/
│       └── static/
├── docs/
│   ├── llm-local.md         # Como usar Ollama
│   ├── frontend-local.md    # Frontend web
│   └── obsidian.md          # Configuração Obsidian
├── config.yaml              # Configuração principal
├── .env.example             # Template de variáveis sensíveis
├── requirements.txt
├── test_summarizer_mock.py  # Testes unitários do summarizer (sem rede)
├── test_web_app.py          # Testes do frontend (TestClient)
├── test_pipeline.py         # Teste end-to-end com transcrição mockada
├── start_watcher.bat        # Atalho Windows para watcher
├── start_web.bat            # Atalho Windows para frontend
└── README.md
```

---

## Testes

Sem rede / sem Ollama / sem Claude API:

```bash
# Summarizer (factory + parsing + erros)
python test_summarizer_mock.py

# Frontend local (todas as rotas)
python test_web_app.py
```

Com Claude API configurado (faz chamada real):

```bash
python test_pipeline.py
```

---

## Solução de problemas

| Sintoma                                                        | Causa / fix                                                          |
|----------------------------------------------------------------|----------------------------------------------------------------------|
| `ffmpeg não encontrado no PATH`                                | Instale: `winget install Gyan.FFmpeg`                                |
| `whisper-cli nao encontrado em ...`                            | Coloque o binário em `.whisper-cpp/`                                 |
| `Modelo nao encontrado em ...`                                 | Baixe o ggml em `.models/`                                           |
| `Chave da API Anthropic inválida`                              | Confira `ANTHROPIC_API_KEY` no `.env`                                |
| `Não foi possível conectar ao Ollama`                          | Inicie o app/serviço Ollama (`ollama serve`)                         |
| `Ollama respondeu 404. ... ollama pull qwen2.5:14b`            | Modelo não baixado: `ollama pull qwen2.5:14b`                        |
| Frontend mostra 0 reuniões                                      | Verifique `vault_dir` em `config.yaml` e se há pastas em `wiki/reunioes/` |
| Watcher detecta arquivo mas não processa                       | Confira `meeting_processor.log`. OBS ainda gravando? Espere 10 s.    |
| Resumo incompleto em reunião muito longa                       | Aumente `ollama_num_ctx` ou troque para Claude API                   |

---

## Roadmap / contribuições

PRs e issues bem-vindos. Ideias na fila:

- [ ] Diarização de falantes (`pyannote.audio` ou `whisperX`).
- [ ] Suporte a múltiplas reuniões em paralelo (worker pool).
- [ ] Webhook out (post-process) para integrar com Slack/Teams/Notion.
- [ ] Streaming do resumo no frontend via SSE.
- [ ] Edição inline das tarefas direto pelo frontend (escreve de volta no `.md`).

---

## Licença

MIT — veja [`LICENSE`](LICENSE).
