"""Diarização de falantes via pyannote (opcional, com degradação graciosa)."""
from __future__ import annotations

import logging

from .config import Settings
from .models import TranscriptSegment

logger = logging.getLogger(__name__)


def diarize(audio_path, config: Settings) -> list[tuple[float, float, str]]:
    """Roda o pyannote e devolve [(start, end, label_bruto)] — [] em qualquer falha.

    pyannote é dependência opcional: import preguiçoso aqui dentro. Token/modelo
    inválidos, pacote ausente ou erro de runtime nunca propagam — devolvem [].
    """
    try:
        from pyannote.audio import Pipeline
        import torch

        pipeline = Pipeline.from_pretrained(
            config.diarization_model, token=config.hf_token or None
        )
        if pipeline is None:
            logger.warning(
                "pyannote retornou None (token/condições do modelo?). Diarizacao desligada."
            )
            return []
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        diar = pipeline(str(audio_path))
        return [
            (turn.start, turn.end, label)
            for turn, _, label in diar.itertracks(yield_label=True)
        ]
    except Exception as e:  # noqa: BLE001 — diarizacao nunca derruba o pipeline
        logger.warning("Falha na diarizacao (%s). Seguindo sem falantes.", e)
        return []


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[tuple[float, float, str]],
) -> None:
    """Atribui a cada segmento o falante (Falante N) do turno de maior sobreposição.

    Rótulos brutos do pyannote (SPEAKER_00, ...) viram "Falante 1/2/..." na ordem
    de primeira aparição. Segmento sem sobreposição positiva fica com speaker None.
    Muta os segmentos no lugar.
    """
    friendly: dict[str, str] = {}
    for _s, _e, label in turns:
        if label not in friendly:
            friendly[label] = f"Falante {len(friendly) + 1}"

    for seg in segments:
        best_label = None
        best_overlap = 0.0
        for t_start, t_end, label in turns:
            overlap = min(seg.end, t_end) - max(seg.start, t_start)
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = label
        seg.speaker = friendly[best_label] if best_label is not None else None
