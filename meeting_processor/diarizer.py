"""Diarização de falantes via pyannote (opcional, com degradação graciosa)."""
from __future__ import annotations

import logging

from .config import Settings
from .models import TranscriptSegment

logger = logging.getLogger(__name__)


def _parse_diarization(result):
    """Extrai (turns, {raw_label: vetor}) da saída do pyannote (3.1 tupla / community-1 objeto)."""
    if isinstance(result, tuple) and len(result) == 2:
        ann, emb = result
    else:
        ann = getattr(result, "speaker_diarization", result)
        # pyannote 4.x DiarizeOutput expõe os vetores em `speaker_embeddings`
        # ((num_speakers, dim), na ordem de speaker_diarization.labels()).
        # `embeddings` é fallback p/ APIs antigas que usavam esse nome.
        emb = getattr(result, "speaker_embeddings", None)
        if emb is None:
            emb = getattr(result, "embeddings", None)
    ann = getattr(ann, "speaker_diarization", ann)
    labels = list(ann.labels())
    turns = [(t.start, t.end, lbl) for t, _, lbl in ann.itertracks(yield_label=True)]
    emb_by_raw: dict[str, list[float]] = {}
    if emb is not None:
        for i, lbl in enumerate(labels):
            try:
                emb_by_raw[lbl] = [float(x) for x in emb[i]]
            except Exception:  # noqa: BLE001
                pass
    return turns, emb_by_raw


def diarize(audio_path, config: Settings) -> tuple[list[tuple[float, float, str]], dict[str, list[float]]]:
    """Roda o pyannote e devolve ([(start, end, label_bruto)], {label: embedding}).

    pyannote é dependência opcional: import preguiçoso aqui dentro. Token/modelo
    inválidos, pacote ausente ou erro de runtime nunca propagam — devolvem ([], {}).
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
            return [], {}
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        # pyannote 4.x já devolve um DiarizeOutput com speaker_embeddings; o antigo
        # kwarg return_embeddings é ignorado (só gera warning), então não o passamos.
        result = pipeline(str(audio_path))
        return _parse_diarization(result)
    except Exception as e:  # noqa: BLE001 — diarizacao nunca derruba o pipeline
        logger.warning("Falha na diarizacao (%s). Seguindo sem falantes.", e)
        return [], {}


def assign_speakers(
    segments: list[TranscriptSegment],
    turns: list[tuple[float, float, str]],
) -> dict[str, str]:
    """Atribui a cada segmento o falante (Falante N) do turno de maior sobreposição.

    Rótulos brutos do pyannote (SPEAKER_00, ...) viram "Falante 1/2/..." na ordem
    de primeira aparição. Segmento sem sobreposição positiva fica com speaker None.
    Muta os segmentos no lugar e devolve o mapa {rótulo bruto: "Falante N"}.
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
    return friendly
