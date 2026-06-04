"""Carregamento e validação de configuração."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class KanbanColumns(BaseModel):
    todo: str = "A Fazer"
    in_progress: str = "Em Progresso"
    done: str = "Concluído"


class Settings(BaseModel):
    # Caminhos
    # watch_dir vazio => auto-detecta ~/Videos/OBS (resolvido em load_config).
    # Editável pela interface web ou via env MEETING_WATCH_DIR.
    watch_dir: str = ""
    vault_dir: str = "./vault"

    # Monitoramento
    watch_extensions: list[str] = [".mkv", ".mp4", ".webm"]
    file_stable_seconds: int = 10

    # Whisper
    whisper_model: str = "base"
    whisper_language: str = "pt"
    whisper_device: str = "cpu"
    whisper_initial_prompt: str = "Transcrição de reunião em português brasileiro."
    # Backend de transcrição:
    #   "auto"   -> usa whisper.cpp se encontrado, senão openai-whisper (pip)
    #   "cpp"    -> força whisper.cpp (mais rápido com GPU)
    #   "openai" -> força openai-whisper (Python puro, baixa o modelo sozinho)
    whisper_backend: str = "auto"
    # Caminhos do whisper.cpp. Vazio => detecta automaticamente no PATH
    # do sistema e em .whisper-cpp/ e .models/ dentro do projeto.
    whisper_cli_path: str = ""
    whisper_model_path: str = ""

    # ---------------------------------------------------------------
    # LLM (provedor de resumo)
    # ---------------------------------------------------------------
    # Provedor de LLM usado pelo summarizer.
    #   "anthropic" -> Claude API (requer ANTHROPIC_API_KEY)
    #   "openai"    -> OpenAI e compatíveis (requer OPENAI_API_KEY)
    #   "gemini"    -> Google Gemini (requer GEMINI_API_KEY)
    #   "local" / "ollama" -> Ollama local (requer servidor rodando)
    #   "none"      -> não usa LLM: só transcreve (sem resumo/nota/kanban/wiki)
    llm_provider: str = "anthropic"

    # Claude API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI e qualquer serviço compatível com a API da OpenAI
    # (OpenRouter, Groq, DeepSeek, xAI/Grok, Mistral, Azure, ...).
    # Para usar outro serviço, basta trocar openai_base_url + OPENAI_API_KEY.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    openai_request_timeout: float = 600.0

    # Google Gemini (API nativa)
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-2.0-flash"
    gemini_request_timeout: float = 600.0

    # Ollama (LLM local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:14b"
    ollama_temperature: float = 0.2
    # Janela de contexto. qwen2.5 suporta até 32k. Reuniões longas
    # se beneficiam de contexto maior — ajuste conforme sua VRAM/RAM.
    ollama_num_ctx: int = 16384
    ollama_request_timeout: float = 600.0

    # Comum a todos os provedores
    summary_chunk_minutes: int = 5
    max_tokens_summary: int = 4096

    # ---------------------------------------------------------------
    # Etapas do pipeline (áudio + transcrição sempre rodam)
    # ---------------------------------------------------------------
    # Desligar o resumo => modo "só transcrição": salva a transcrição
    # no vault e para. Nota/Kanban/Wiki dependem do resumo e são
    # desligados automaticamente quando o resumo está off.
    enable_summary: bool = True
    enable_note: bool = True
    enable_kanban: bool = True
    enable_wiki: bool = True

    # Nota
    default_tags: list[str] = ["meeting", "transcription", "source"]
    note_status: str = "mature"

    # Kanban
    kanban_file: str = "wiki/kanban-reunioes.md"
    kanban_columns: KanbanColumns = KanbanColumns()

    # Processamento
    temp_dir: str = ".tmp"
    cleanup_temp: bool = True
    log_level: str = "INFO"

    # Caminhos resolvidos
    project_root: str = ""

    @property
    def vault_path(self) -> Path:
        return Path(self.project_root) / self.vault_dir

    @property
    def watch_path(self) -> Path:
        return Path(self.watch_dir).expanduser()

    @property
    def temp_path(self) -> Path:
        return Path(self.project_root) / self.temp_dir

    @property
    def kanban_path(self) -> Path:
        return self.vault_path / self.kanban_file

    @property
    def raw_transcriptions_path(self) -> Path:
        return self.vault_path / ".raw" / "transcriptions"

    @property
    def meetings_path(self) -> Path:
        return self.vault_path / "wiki" / "meetings"

    @property
    def reunioes_path(self) -> Path:
        return self.vault_path / "wiki" / "reunioes"

    def steps(self) -> dict[str, bool]:
        """Etapas efetivas, já resolvendo dependências.

        Nota/Kanban/Wiki só fazem sentido com o resumo ligado. Com
        ``llm_provider="none"`` nenhuma LLM roda — só a transcrição.
        """
        summary = self.enable_summary and (self.llm_provider or "").lower() != "none"
        return {
            "summary": summary,
            "note": summary and self.enable_note,
            "kanban": summary and self.enable_kanban,
            "wiki": summary and self.enable_wiki,
        }


def load_config(config_path: str | None = None) -> Settings:
    """Carrega configuração do YAML e variáveis de ambiente."""
    project_root = Path(__file__).parent.parent
    load_dotenv(project_root / ".env")

    if config_path is None:
        config_path = str(project_root / "config.yaml")

    config_data: dict = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}

    # Override com variáveis de ambiente
    # Mapeamento: ENV -> chave de Settings (cast quando necessário)
    string_overrides = {
        "MEETING_WATCH_DIR": "watch_dir",
        "MEETING_VAULT_DIR": "vault_dir",
        "MEETING_WHISPER_MODEL": "whisper_model",
        "MEETING_WHISPER_LANGUAGE": "whisper_language",
        "MEETING_WHISPER_DEVICE": "whisper_device",
        "MEETING_WHISPER_BACKEND": "whisper_backend",
        "MEETING_WHISPER_CLI_PATH": "whisper_cli_path",
        "MEETING_WHISPER_MODEL_PATH": "whisper_model_path",
        "MEETING_ANTHROPIC_MODEL": "anthropic_model",
        "MEETING_LOG_LEVEL": "log_level",
        # LLM
        "MEETING_LLM_PROVIDER": "llm_provider",
        "MEETING_OPENAI_BASE_URL": "openai_base_url",
        "MEETING_OPENAI_MODEL": "openai_model",
        "MEETING_GEMINI_BASE_URL": "gemini_base_url",
        "MEETING_GEMINI_MODEL": "gemini_model",
        "MEETING_OLLAMA_BASE_URL": "ollama_base_url",
        "MEETING_OLLAMA_MODEL": "ollama_model",
    }
    for env_key, config_key in string_overrides.items():
        env_val = os.environ.get(env_key)
        if env_val is not None and env_val != "":
            config_data[config_key] = env_val

    # Overrides numéricos
    float_overrides = {
        "MEETING_OLLAMA_TEMPERATURE": "ollama_temperature",
        "MEETING_OLLAMA_REQUEST_TIMEOUT": "ollama_request_timeout",
    }
    for env_key, config_key in float_overrides.items():
        env_val = os.environ.get(env_key)
        if env_val is not None and env_val != "":
            try:
                config_data[config_key] = float(env_val)
            except ValueError:
                pass

    int_overrides = {
        "MEETING_OLLAMA_NUM_CTX": "ollama_num_ctx",
    }
    for env_key, config_key in int_overrides.items():
        env_val = os.environ.get(env_key)
        if env_val is not None and env_val != "":
            try:
                config_data[config_key] = int(env_val)
            except ValueError:
                pass

    # Etapas do pipeline (booleanos)
    bool_overrides = {
        "MEETING_ENABLE_SUMMARY": "enable_summary",
        "MEETING_ENABLE_NOTE": "enable_note",
        "MEETING_ENABLE_KANBAN": "enable_kanban",
        "MEETING_ENABLE_WIKI": "enable_wiki",
    }
    for env_key, config_key in bool_overrides.items():
        env_val = os.environ.get(env_key)
        if env_val is not None and env_val != "":
            config_data[config_key] = env_val.strip().lower() in (
                "1", "true", "yes", "on", "sim",
            )

    config_data["anthropic_api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
    config_data["openai_api_key"] = os.environ.get("OPENAI_API_KEY", "")
    config_data["gemini_api_key"] = os.environ.get(
        "GEMINI_API_KEY", os.environ.get("GOOGLE_API_KEY", "")
    )
    config_data["project_root"] = str(project_root)

    # Default portável para a pasta monitorada: ~/Videos/OBS.
    # Funciona em Windows, macOS e Linux sem caminho hardcoded.
    if not config_data.get("watch_dir"):
        config_data["watch_dir"] = str(Path.home() / "Videos" / "OBS")

    settings = Settings(**config_data)

    # Criar diretórios necessários
    settings.temp_path.mkdir(parents=True, exist_ok=True)
    settings.raw_transcriptions_path.mkdir(parents=True, exist_ok=True)
    settings.reunioes_path.mkdir(parents=True, exist_ok=True)

    return settings
