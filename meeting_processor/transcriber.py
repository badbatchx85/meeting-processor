"""Transcrição via whisper.cpp (CPU ou GPU)."""

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import Settings
from .models import Transcript, TranscriptSegment, WordTime
from .utils import parse_timestamp

logger = logging.getLogger(__name__)

# Duração do áudio (s) -> modelo Whisper, no modo adaptativo. Acima do último
# limite, usa "small". Limites medidos no benchmark de qualidade/velocidade.
_ADAPTIVE_TIERS: tuple[tuple[int, str], ...] = ((20 * 60, "large"), (45 * 60, "medium"))


def select_whisper_model(duration_s: float, configured_model: str) -> str:
    """Escolhe o modelo Whisper pela duração do áudio (modo adaptativo).

    Duração desconhecida (<= 0, ex.: ffprobe falhou) mantém o modelo configurado
    — não degradamos a qualidade sem saber o tamanho.
    """
    if duration_s <= 0:
        return configured_model
    for limit, model in _ADAPTIVE_TIERS:
        if duration_s <= limit:
            return model
    return "small"


_FASTER_NAMES = {"large": "large-v3"}


def _faster_model_name(name: str) -> str:
    """openai-whisper -> id do faster-whisper (large -> large-v3); resto passa direto."""
    return _FASTER_NAMES.get(name, name)


def _debug_logger(config: Settings) -> logging.Logger:
    """Logger dedicado que grava ``whisper-debug.log`` na raiz do projeto.

    Sempre em DEBUG, com handler próprio e ``propagate=False`` para não duplicar
    no log principal nem no console. Idempotente: mantém um único FileHandler
    apontando para o arquivo atual (re-aponta se ``project_root`` mudar).
    """
    path = str(Path(config.project_root) / "whisper-debug.log")
    abspath = os.path.abspath(path)
    log = logging.getLogger("meeting_processor.whisper_debug")
    log.setLevel(logging.DEBUG)
    log.propagate = False

    already = any(
        isinstance(h, logging.FileHandler)
        and os.path.abspath(h.baseFilename) == abspath
        for h in log.handlers
    )
    if not already:
        for h in list(log.handlers):
            log.removeHandler(h)
            h.close()
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
            )
        )
        log.addHandler(handler)
    return log


def _log_run_failure(
    config: Settings, backend: str, context: dict, exc: BaseException
) -> None:
    """Registra a falha do Whisper com traceback completo nos dois logs."""
    _debug_logger(config).error(
        "FALHA backend=%s contexto=%s", backend, context, exc_info=exc
    )
    logger.error("Whisper falhou (backend=%s): %s", backend, exc, exc_info=exc)


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
    """Transcreve áudio com Whisper.

    Dois backends, escolhidos por ``config.whisper_backend``:
      - ``cpp``: whisper.cpp (binário; mais rápido com GPU)
      - ``openai``: openai-whisper (Python puro; baixa o modelo sozinho)
      - ``auto`` (padrão): usa whisper.cpp se encontrado, senão openai-whisper.
    """

    def __init__(self, config: Settings):
        self.config = config

    def transcribe(
        self, audio_path: Path, progress_callback=None, model: str | None = None
    ) -> Transcript:
        """Transcreve um arquivo de áudio escolhendo o backend disponível.

        ``model`` sobrescreve ``config.whisper_model`` apenas no backend
        openai-whisper (o whisper.cpp usa um .bin fixo e ignora o override).
        """
        backend = (self.config.whisper_backend or "faster").lower()
        if backend == "openai":
            return self._transcribe_openai(audio_path, progress_callback, model)
        if backend == "cpp":
            return self._transcribe_cpp(audio_path, progress_callback)
        if backend == "faster":
            return self._transcribe_faster(audio_path, progress_callback, model)
        # auto: faster-whisper, senão whisper.cpp, senão openai
        import importlib.util
        if importlib.util.find_spec("faster_whisper") is not None:
            return self._transcribe_faster(audio_path, progress_callback, model)
        if resolve_whisper_cli(self.config) is not None and resolve_whisper_model(self.config) is not None:
            return self._transcribe_cpp(audio_path, progress_callback)
        logger.info("whisper.cpp nao encontrado; usando openai-whisper (pip).")
        return self._transcribe_openai(audio_path, progress_callback, model)

    # -- Backend: openai-whisper (Python puro) -------------------------------

    def _transcribe_openai(
        self, audio_path: Path, progress_callback=None, model: str | None = None
    ) -> Transcript:
        try:
            import whisper  # openai-whisper
        except ImportError as e:
            raise RuntimeError(
                "openai-whisper não instalado. Rode: pip install -r requirements.txt"
            ) from e

        model_name = model or self.config.whisper_model

        if progress_callback:
            progress_callback(5, f"Carregando modelo {model_name}...")
        logger.info(
            "Transcrevendo %s com openai-whisper (modelo=%s)...",
            audio_path.name,
            model_name,
        )

        dbg = _debug_logger(self.config)
        size_mb = audio_path.stat().st_size / 1e6 if audio_path.exists() else 0.0
        ctx = {
            "model": model_name,
            "language": self.config.whisper_language,
            "audio": str(audio_path),
            "audio_mb": round(size_mb, 1),
        }
        dbg.debug(
            "Início openai-whisper: model=%s lang=%s audio=%s (%.1f MB) initial_prompt=%s",
            model_name,
            self.config.whisper_language,
            audio_path.name,
            size_mb,
            bool(self.config.whisper_initial_prompt),
        )
        dbg.debug(
            "Se o modelo não estiver em cache (~/.cache/whisper), será baixado "
            "agora — pode demorar (carga lenta = download)."
        )

        try:
            t0 = time.monotonic()
            model = whisper.load_model(model_name)
            dbg.debug(
                "Modelo carregado em %.1fs (device=%s)",
                time.monotonic() - t0,
                getattr(model, "device", "?"),
            )
            if progress_callback:
                progress_callback(15, "Transcrevendo áudio...")

            t1 = time.monotonic()
            result = model.transcribe(
                str(audio_path),
                language=self.config.whisper_language,
                initial_prompt=self.config.whisper_initial_prompt or None,
            )
            dbg.debug("model.transcribe concluído em %.1fs", time.monotonic() - t1)
        except Exception as e:  # noqa: BLE001 — registra contexto e repropaga
            _log_run_failure(self.config, "openai", ctx, e)
            raise

        segments = []
        for seg in result.get("segments", []):
            text = (seg.get("text") or "").strip()
            if text:
                segments.append(
                    TranscriptSegment(
                        start=float(seg.get("start", 0.0)),
                        end=float(seg.get("end", 0.0)),
                        text=text,
                    )
                )

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

    # -- Backend: faster-whisper (CTranslate2) --------------------------------

    def _transcribe_faster(self, audio_path, progress_callback=None, model=None):
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            logger.warning("faster-whisper não instalado; usando openai-whisper.")
            return self._transcribe_openai(audio_path, progress_callback, model)

        model_name = _faster_model_name(model or self.config.whisper_model)
        ctx = {"model": model_name}
        try:
            wm = WhisperModel(
                model_name,
                device=self.config.whisper_device,
                compute_type=self.config.whisper_compute_type,
            )
            if progress_callback:
                progress_callback(15, "Transcrevendo áudio (faster-whisper)...")
            seg_iter, info = wm.transcribe(
                str(audio_path),
                language=self.config.whisper_language,
                initial_prompt=self.config.whisper_initial_prompt or None,
                vad_filter=True,
                word_timestamps=True,
            )
            segments = []
            for s in seg_iter:
                text = (s.text or "").strip()
                if not text:
                    continue
                words = [
                    WordTime(start=float(w.start), end=float(w.end), text=(w.word or "").strip())
                    for w in (getattr(s, "words", None) or [])
                    if (w.word or "").strip()
                ] or None
                segments.append(
                    TranscriptSegment(start=float(s.start), end=float(s.end), text=text, words=words)
                )
        except Exception as e:  # noqa: BLE001
            _log_run_failure(self.config, "faster", ctx, e)
            raise

        duration = float(getattr(info, "duration", 0.0)) or (segments[-1].end if segments else 0.0)
        full_text = " ".join(s.text for s in segments)
        if progress_callback:
            progress_callback(100, f"{len(segments)} segmentos, {duration/60:.1f} min")
        logger.info("Transcrição (faster-whisper): %d segmentos, %.1f min.", len(segments), duration / 60)
        return Transcript(
            segments=segments, full_text=full_text,
            language=self.config.whisper_language, duration=duration,
        )

    # -- Backend: whisper.cpp (binário) --------------------------------------

    def _transcribe_cpp(self, audio_path: Path, progress_callback=None) -> Transcript:
        cli = resolve_whisper_cli(self.config)
        if cli is None:
            raise RuntimeError(
                "Executável do whisper.cpp não encontrado. Instale o whisper.cpp "
                "e deixe-o no PATH, coloque o binário em .whisper-cpp/, ou defina "
                "whisper_cli_path no config.yaml (ou a env MEETING_WHISPER_CLI_PATH). "
                "Alternativa sem build: use whisper_backend=openai."
            )
        model = resolve_whisper_model(self.config)
        if model is None:
            raise RuntimeError(
                "Modelo do Whisper (.bin) não encontrado. Baixe um modelo GGML para "
                ".models/, ou defina whisper_model_path no config.yaml "
                "(ou a env MEETING_WHISPER_MODEL_PATH)."
            )

        if progress_callback:
            progress_callback(5, "Iniciando whisper.cpp...")

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

        dbg = _debug_logger(self.config)
        ctx = {"cmd": " ".join(cmd), "model": str(model), "audio": str(audio_path)}
        dbg.debug("Início whisper.cpp: cmd=%s", " ".join(cmd))

        try:
            t0 = time.monotonic()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
                errors="replace",
            )
            dbg.debug(
                "whisper.cpp ok em %.1fs (rc=%d) stderr=%s",
                time.monotonic() - t0,
                result.returncode,
                result.stderr,
            )
        except subprocess.CalledProcessError as e:
            ctx["returncode"] = e.returncode
            ctx["stderr"] = e.stderr  # completo, sem truncar, no whisper-debug.log
            _log_run_failure(self.config, "cpp", ctx, e)
            raise RuntimeError(f"whisper-cli falhou: {(e.stderr or '')[:200]}") from e

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
                err = RuntimeError("whisper-cli nao gerou saida JSON valida")
                _log_run_failure(self.config, "cpp", ctx, err)
                raise err

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
