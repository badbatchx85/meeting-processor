"""Extração de áudio de arquivos de vídeo usando ffmpeg."""

import logging
import subprocess
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)


def validate_ffmpeg() -> bool:
    """Verifica se o ffmpeg está disponível no PATH."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def get_duration(file_path: Path) -> float:
    """Retorna a duração do arquivo em segundos usando ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.warning("Não foi possível obter duração de %s: %s", file_path, e)
        return 0.0


def extract_audio(video_path: Path, config: Settings) -> Path:
    """Extrai áudio WAV 16kHz mono do vídeo para transcrição com Whisper.

    Args:
        video_path: Caminho do arquivo de vídeo.
        config: Configurações do sistema.

    Returns:
        Caminho do arquivo WAV extraído.

    Raises:
        RuntimeError: Se o ffmpeg não estiver instalado ou a extração falhar.
    """
    if not validate_ffmpeg():
        raise RuntimeError(
            "ffmpeg não encontrado no PATH. "
            "Instale com: winget install Gyan.FFmpeg"
        )

    output_path = config.temp_path / f"{video_path.stem}.wav"
    config.temp_path.mkdir(parents=True, exist_ok=True)

    logger.info("Extraindo áudio de %s...", video_path.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-i", str(video_path),
                "-vn",                  # sem vídeo
                "-acodec", "pcm_s16le", # WAV PCM 16-bit
                "-ar", "16000",         # 16kHz (padrão Whisper)
                "-ac", "1",             # mono
                "-y",                   # sobrescrever se existir
                str(output_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Falha ao extrair áudio: {e.stderr}"
        ) from e

    logger.info("Áudio extraído: %s (%.1f MB)", output_path.name, output_path.stat().st_size / 1_048_576)
    return output_path
