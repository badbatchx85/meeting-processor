"""Transcrição via whisper.cpp com Vulkan (GPU AMD)."""

import json
import logging
import subprocess
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)

WHISPER_CLI = Path(__file__).parent.parent / ".whisper-cpp" / "whisper-cli.exe"
MODEL_PATH = Path(__file__).parent.parent / ".models" / "ggml-large-v3-turbo.bin"


class WhisperTranscriber:
    """Transcreve áudio usando whisper.cpp com aceleração Vulkan (AMD GPU)."""

    def __init__(self, config: Settings):
        self.config = config

    def transcribe(self, audio_path: Path, progress_callback=None) -> Transcript:
        """Transcreve um arquivo de áudio via whisper-cli com GPU Vulkan."""
        if not WHISPER_CLI.exists():
            raise RuntimeError(f"whisper-cli nao encontrado em: {WHISPER_CLI}")
        if not MODEL_PATH.exists():
            raise RuntimeError(f"Modelo nao encontrado em: {MODEL_PATH}")

        if progress_callback:
            progress_callback(5, "Iniciando whisper.cpp (Vulkan/GPU)...")

        logger.info("Transcrevendo %s com whisper.cpp (Vulkan)...", audio_path.name)

        # whisper-cli com saída JSON para pegar timestamps
        cmd = [
            str(WHISPER_CLI),
            "-m", str(MODEL_PATH),
            "-f", str(audio_path),
            "-l", self.config.whisper_language,
            "-oj",          # output JSON
            "--no-prints",  # sem logs extras no stdout
        ]

        if progress_callback:
            progress_callback(10, "Transcrevendo com GPU AMD...")

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
            t0 = self._parse_timestamp(seg.get("timestamps", {}).get("from", "00:00:00"))
            t1 = self._parse_timestamp(seg.get("timestamps", {}).get("to", "00:00:00"))
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

    @staticmethod
    def _parse_timestamp(ts: str) -> float:
        """Converte 'HH:MM:SS.mmm' ou 'HH:MM:SS,mmm' para segundos."""
        ts = ts.replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        return 0.0
