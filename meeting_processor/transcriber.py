"""Transcrição via whisper.cpp (CPU ou GPU)."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment
from .utils import parse_timestamp

logger = logging.getLogger(__name__)

# Nomes do executável do whisper.cpp procurados no PATH do sistema.
# Apenas nomes específicos — "main" (binário legado) é genérico demais e
# casaria com programas não relacionados (ex.: main.CPL no Windows).
_CLI_NAMES_PATH = ("whisper-cli", "whisper-cpp")
# Nomes aceitos dentro de .whisper-cpp/ no projeto, onde o contexto é claro.
_CLI_NAMES_LOCAL = ("whisper-cli", "whisper-cpp", "main")


def resolve_whisper_cli(config: Settings) -> Path | None:
    """Localiza o executável do whisper.cpp de forma portável.

    Ordem: caminho explícito na config -> PATH do sistema -> .whisper-cpp/
    dentro do projeto (com ou sem extensão .exe).
    """
    if config.whisper_cli_path:
        p = Path(config.whisper_cli_path).expanduser()
        if p.exists():
            return p

    for name in _CLI_NAMES_PATH:
        found = shutil.which(name)
        if found:
            return Path(found)

    local_dir = Path(config.project_root) / ".whisper-cpp"
    for name in _CLI_NAMES_LOCAL:
        for candidate in (local_dir / name, local_dir / f"{name}.exe"):
            if candidate.exists():
                return candidate
    return None


def resolve_whisper_model(config: Settings) -> Path | None:
    """Localiza o modelo GGML de forma portável.

    Ordem: caminho explícito na config -> primeiro ``*.bin`` em .models/.
    """
    if config.whisper_model_path:
        p = Path(config.whisper_model_path).expanduser()
        if p.exists():
            return p

    models_dir = Path(config.project_root) / ".models"
    if models_dir.is_dir():
        models = sorted(models_dir.glob("*.bin"))
        if models:
            return models[0]
    return None


class WhisperTranscriber:
    """Transcreve áudio usando whisper.cpp (aceleração por GPU quando disponível)."""

    def __init__(self, config: Settings):
        self.config = config

    def transcribe(self, audio_path: Path, progress_callback=None) -> Transcript:
        """Transcreve um arquivo de áudio via whisper-cli."""
        cli = resolve_whisper_cli(self.config)
        if cli is None:
            raise RuntimeError(
                "Executável do whisper.cpp não encontrado. Instale o whisper.cpp "
                "e deixe-o no PATH, coloque o binário em .whisper-cpp/, ou defina "
                "whisper_cli_path no config.yaml (ou a env MEETING_WHISPER_CLI_PATH)."
            )
        model = resolve_whisper_model(self.config)
        if model is None:
            raise RuntimeError(
                "Modelo do Whisper (.bin) não encontrado. Baixe um modelo GGML para "
                ".models/, ou defina whisper_model_path no config.yaml "
                "(ou a env MEETING_WHISPER_MODEL_PATH)."
            )

        if progress_callback:
            progress_callback(5, "Iniciando whisper.cpp (Vulkan/GPU)...")

        logger.info("Transcrevendo %s com whisper.cpp...", audio_path.name)

        # whisper-cli com saída JSON para pegar timestamps
        cmd = [
            str(cli),
            "-m", str(model),
            "-f", str(audio_path),
            "-l", self.config.whisper_language,
            "-oj",          # output JSON
            "--no-prints",  # sem logs extras no stdout
        ]

        if progress_callback:
            progress_callback(10, "Transcrevendo áudio...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.CalledProcessError as e:
            logger.error("Erro no whisper-cli: %s", e.stderr[:500])
            raise RuntimeError(f"whisper-cli falhou: {e.stderr[:200]}") from e

        # Parse JSON output
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Fallback: tentar encontrar o arquivo JSON gerado
            json_path = audio_path.with_suffix(".wav.json")
            if json_path.exists():
                data = json.loads(json_path.read_text(encoding="utf-8"))
                json_path.unlink()
            else:
                raise RuntimeError("whisper-cli nao gerou saida JSON valida")

        # Extrair segmentos
        segments = []
        for seg in data.get("transcription", []):
            t0 = parse_timestamp(seg.get("timestamps", {}).get("from", "00:00:00"))
            t1 = parse_timestamp(seg.get("timestamps", {}).get("to", "00:00:00"))
            text = seg.get("text", "").strip()
            if text:
                segments.append(TranscriptSegment(start=t0, end=t1, text=text))

        duration = segments[-1].end if segments else 0.0
        full_text = " ".join(seg.text for seg in segments)

        if progress_callback:
            progress_callback(100, f"{len(segments)} segmentos, {duration/60:.1f} min")

        logger.info(
            "Transcrição concluída: %d segmentos, %.1f minutos.",
            len(segments),
            duration / 60,
        )

        return Transcript(
            segments=segments,
            full_text=full_text,
            language=self.config.whisper_language,
            duration=duration,
        )
