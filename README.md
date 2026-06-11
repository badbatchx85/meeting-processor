# Meeting Processor

> Transforma gravações de reuniões em **transcrição**, **resumo**, **tarefas**
> e **Kanban** — rodando **100% na sua máquina** (Windows, macOS ou Linux).

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## O que ele faz

1. Você grava a reunião (OBS ou qualquer vídeo).
2. Ele **extrai o áudio** (ffmpeg) e **transcreve** (Whisper).
3. Opcionalmente **resume** com uma LLM (Claude API ou Ollama local) e gera
   nota, lista de tarefas e quadro Kanban.
4. Você lê o resultado pelo **navegador** ou pelo **Obsidian**.

Você escolhe **quais etapas rodar** — pode usar só a transcrição, por exemplo.

---

## Instalação — passo a passo

Funciona igual nos três sistemas. Onde o comando muda, há uma linha para cada SO.

### Passo 1 — Instale o Python 3.11+

Confira se já tem:

```bash
python --version      # Windows
python3 --version     # macOS / Linux
```

Se não tiver, baixe em <https://www.python.org/downloads/> (no Windows, marque
**"Add Python to PATH"** durante a instalação).

### Passo 2 — Instale o ffmpeg

| Sistema | Comando |
|---------|---------|
| Windows | `winget install Gyan.FFmpeg` |
| macOS   | `brew install ffmpeg` |
| Linux   | `sudo apt install ffmpeg` |

Confira: `ffmpeg -version`

### Passo 3 — Baixe o projeto e instale as dependências

```bash
git clone https://github.com/Alencar-png/meeting-processor.git
cd meeting-processor
```

Crie o ambiente virtual e instale:

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

> Pronto para transcrever. O Whisper roda direto via `pip` (baixa o modelo
> sozinho na primeira vez). Para resumos com IA, faça o passo 4.

### Passo 4 *(opcional)* — Ative o resumo com IA

Primeiro copie o `.env.example` para `.env`
(`copy .env.example .env` no Windows, `cp .env.example .env` no macOS/Linux).
Depois escolha **um** provedor e preencha a chave no `.env`:

| Provedor | `MEETING_LLM_PROVIDER` | Chave no `.env` | Onde obter |
|----------|------------------------|-----------------|------------|
| **Claude** | `anthropic` | `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> |
| **OpenAI** | `openai` | `OPENAI_API_KEY` | <https://platform.openai.com/> |
| **Gemini** | `gemini` | `GEMINI_API_KEY` | <https://aistudio.google.com/apikey> |
| **Ollama (local, grátis)** | `local` | — | <https://ollama.com/download> |
| **Sem IA (só transcrição)** | `none` | — | não precisa de nada |

Exemplo (OpenAI):
```dotenv
MEETING_LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
# MEETING_OPENAI_MODEL=gpt-4o
```

Para **Ollama**, instale e baixe um modelo (`ollama pull qwen2.5:14b`), depois
use `MEETING_LLM_PROVIDER=local`.

> Você também troca de provedor pela interface web, sem editar arquivos.
> Sem o passo 4, o sistema funciona em **modo só transcrição**.

**Qualquer outro modelo do mercado** — o provedor `openai` aceita qualquer
serviço compatível com a API da OpenAI: basta trocar `MEETING_OPENAI_BASE_URL`.

| Serviço | Base URL | Exemplo de modelo |
|---------|----------|-------------------|
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4o`, `anthropic/claude-3.5-sonnet` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| xAI (Grok) | `https://api.x.ai/v1` | `grok-2-latest` |

---

## Como usar

A forma mais simples é pelo **navegador**:

```bash
python -m meeting_processor web
```

Abra <http://127.0.0.1:8765>. Na página **Configuração** você define, com cliques:

- a **pasta do OBS** a monitorar (campo editável);
- **quais etapas rodar** (Transcrição é fixa; Resumo, Nota, Kanban e Wiki são opcionais);
- o **provedor de LLM** (Claude ou Ollama);
- ligar/desligar o **watcher** (monitoramento automático).

### Atalhos prontos

| Sistema | Monitorar | Abrir navegador |
|---------|-----------|-----------------|
| Windows | `start_watcher.bat` | `start_web.bat` |
| macOS/Linux | `./start_watcher.sh` | `./start_web.sh` |

*(no macOS/Linux, rode uma vez `chmod +x start_*.sh`)*

### Pela linha de comando

```bash
# Processa um arquivo já gravado
python -m meeting_processor process reuniao.mkv

# Apenas transcrever (sem resumo/nota/kanban/wiki)
python -m meeting_processor process reuniao.mkv --only-transcribe

# Desligar etapas específicas
python -m meeting_processor process reuniao.mkv --no-kanban --no-wiki

# Monitorar a pasta do OBS continuamente
python -m meeting_processor watch
```

---

## Onde fica o resultado

Cada reunião vira uma pasta em `vault/wiki/reunioes/<data hora - nome>/` com:

- `Transcricao - *.md` — transcrição com timestamps (sempre);
- `Resumo - *.md` — resumo executivo + por blocos (se o resumo estiver ligado);
- `Tarefas - *.md` — quadro Kanban (se ligado);
- nota central que liga tudo no grafo do Obsidian.

Abra a pasta `vault/` como **vault do Obsidian**, ou use o **navegador** — os
dois leem os mesmos arquivos.

---

## Escolher o que rodar

Áudio e transcrição **sempre** rodam. As demais são opcionais e podem ser
ligadas/desligadas pela interface, pelo `config.yaml` ou por variável de ambiente:

| Etapa | config.yaml | Variável de ambiente | Depende de |
|-------|-------------|----------------------|------------|
| Resumo (LLM) | `enable_summary` | `MEETING_ENABLE_SUMMARY` | — |
| Nota Obsidian | `enable_note` | `MEETING_ENABLE_NOTE` | Resumo |
| Kanban | `enable_kanban` | `MEETING_ENABLE_KANBAN` | Resumo |
| Wiki | `enable_wiki` | `MEETING_ENABLE_WIKI` | Resumo |

Desligar o **Resumo** equivale ao modo "só transcrição".

---

## Diarização (quem falou)

Opcional. Rotula cada trecho da transcrição com o falante ("Falante 1", "Falante 2"…), rodando localmente após a transcrição.

1. `pip install -r requirements-diarization.txt`
2. Aceite as condições de uso de `pyannote/speaker-diarization-3.1` no Hugging Face.
3. No `.env`: `MEETING_HF_TOKEN=hf_...` e `MEETING_ENABLE_DIARIZATION=true`.
4. Reinicie.

Se estiver desligada ou indisponível (pacote/token ausente), o app se comporta exatamente como antes.

---

## Acelerar com GPU (opcional)

O backend padrão (`openai-whisper`) é simples e funciona em qualquer máquina,
mas pode ser lento sem GPU. Para máxima velocidade, use o **whisper.cpp**:

1. Baixe o binário em <https://github.com/ggerganov/whisper.cpp/releases> e
   coloque em `.whisper-cpp/` (ou deixe no PATH do sistema).
2. Baixe um modelo GGML em
   <https://huggingface.co/ggerganov/whisper.cpp/tree/main> para `.models/`.
3. No `config.yaml`: `whisper_backend: "cpp"` (ou deixe `"auto"`, que usa o
   whisper.cpp automaticamente quando ele está presente).

---

## Solução de problemas

| Sintoma | O que fazer |
|---------|-------------|
| `ffmpeg não encontrado no PATH` | Refaça o **Passo 2** e reabra o terminal |
| Transcrição muito lenta | Use um modelo menor (`whisper_model: "base"`) ou whisper.cpp com GPU |
| `Chave da API Anthropic inválida` | Confira `ANTHROPIC_API_KEY` no `.env` |
| `Não foi possível conectar ao Ollama` | Inicie o Ollama (`ollama serve`) |
| `Ollama respondeu 404` | Baixe o modelo: `ollama pull qwen2.5:14b` |
| Navegador mostra 0 reuniões | Confira a pasta do OBS em **Configuração** e se há vídeos lá |

Logs detalhados ficam em `meeting_processor.log`.

---

## Para desenvolvedores

```bash
python -m pytest -q          # roda os testes (sem rede)
```

Estrutura principal:

```
meeting_processor/
├── __main__.py        # CLI (watch / web / process)
├── config.py          # configuração (YAML + .env + interface)
├── audio.py           # extração de áudio (ffmpeg)
├── transcriber.py     # Whisper (openai-whisper / whisper.cpp)
├── summarizer.py      # resumo (Claude / OpenAI / Gemini / Ollama)
├── note_generator.py  # notas Markdown para Obsidian
├── kanban.py          # quadros Kanban
├── pipeline.py        # orquestra as etapas escolhidas
├── watcher.py         # monitora a pasta do OBS
├── utils.py           # helpers compartilhados
└── web/               # interface no navegador (FastAPI + HTMX)
```

Documentos extras: [`docs/obsidian.md`](docs/obsidian.md),
[`docs/llm-local.md`](docs/llm-local.md),
[`docs/frontend-local.md`](docs/frontend-local.md).
- Interface moderna (React SPA): veja [`docs/frontend-spa.md`](docs/frontend-spa.md).

---

## Licença

MIT — veja [`LICENSE`](LICENSE).
