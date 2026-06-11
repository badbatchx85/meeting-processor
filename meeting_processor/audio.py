"""Extração de áudio de arquivos de vídeo usando ffmpeg."""

import logging
import subprocess
import sys
from pathlib import Path

from .config import Settings

logger = logging.getLogger(__name__)


def _ffmpeg_install_hint() -> str:
    """Sugestão de instalação do ffmpeg conforme o sistema operacional."""
    if sys.platform == "win32":
        return "Instale com: winget install Gyan.FFmpeg"
    if sys.platform == "darwin":
        return "Instale com: brew install ffmpeg"
    return "Instale com: sudo apt install ffmpeg (ou o gerenciador da sua distro)"


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


def _ffmpeg_cmd(video_path: Path, output_path: Path, audio_filter: str | None) -> list[str]:
    """Monta a linha de comando do ffmpeg, com o filtro de áudio quando houver."""
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",                   # sem vídeo
        "-acodec", "pcm_s16le",  # WAV PCM 16-bit
        "-ar", "16000",          # 16kHz (padrão Whisper)
        "-ac", "1",              # mono
    ]
    if audio_filter:
        cmd += ["-af", audio_filter]
    cmd += ["-y", str(output_path)]
    return cmd


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
            f"ffmpeg não encontrado no PATH. {_ffmpeg_install_hint()}"
        )

    output_path = config.temp_path / f"{video_path.stem}.wav"
    config.temp_path.mkdir(parents=True, exist_ok=True)

    logger.info("Extraindo áudio de %s...", video_path.name)

    audio_filter = config.audio_filter if config.enable_audio_denoise else None
    try:
        subprocess.run(
            _ffmpeg_cmd(video_path, output_path, audio_filter),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        if audio_filter:
            logger.warning(
                "Falha no ffmpeg com filtro de audio. Repetindo sem filtro. (%s)",
                (e.stderr or "").strip()[-300:] or e,
            )
            try:
                subprocess.run(
                    _ffmpeg_cmd(video_path, output_path, None),
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as e2:
                raise RuntimeError(f"Falha ao extrair áudio: {e2.stderr}") from e2
        else:
            raise RuntimeError(f"Falha ao extrair áudio: {e.stderr}") from e

    logger.info("Áudio extraído: %s (%.1f MB)", output_path.name, output_path.stat().st_size / 1_048_576)
    return output_path
