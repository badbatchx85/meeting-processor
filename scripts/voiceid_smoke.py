"""Smoke-test cirúrgico do voice ID — valida embeddings + threshold sem Whisper.

Uso:
    MEETING_HF_TOKEN=hf_xxx \
    MEETING_DIARIZATION_MODEL=pyannote/speaker-diarization-community-1 \
    .venv/bin/python scripts/voiceid_smoke.py <audio-ou-video>

O que checa (a pergunta aberta do voice ID, ver memória diarization-features-status):
  1. diarize() devolve embeddings NÃO-vazios  -> prova que community-1 corrige
     o buraco do 3.1 (que não suporta return_embeddings).
  2. dimensão do vetor é sensata.
  3. enroll + match do MESMO falante -> distância ~0, bem < threshold.
  4. distância entre falantes DIFERENTES (se houver 2+) -> deve ser MAIOR que a
     do mesmo falante; idealmente > threshold. Dá um datapoint real pra tunar 0.45
     mesmo com uma única gravação.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meeting_processor.config import load_config
from meeting_processor import voiceprints
from meeting_processor.diarizer import diarize, _parse_diarization  # noqa: F401


def _cos(a, b):
    return voiceprints._cosine_distance(a, b)


def main() -> int:
    if len(sys.argv) < 2:
        print("uso: voiceid_smoke.py <audio-ou-video>")
        return 2
    audio = Path(sys.argv[1])
    if not audio.exists():
        print(f"arquivo não encontrado: {audio}")
        return 2

    config = load_config()
    config.enable_diarization = True
    print(f"modelo    : {config.diarization_model}")
    print(f"token set : {bool(config.hf_token)}")
    print(f"threshold : {config.voice_id_threshold}")
    if not config.hf_token:
        print("\n[BLOQUEADO] MEETING_HF_TOKEN não definido — pyannote é gated.")
        return 1
    print(f"arquivo   : {audio}\n")

    # Espelha o pipeline real: extrai um WAV 16kHz mono antes de diarizar.
    # Jogar o mp4 cru no pyannote estoura a asserção de samples por chunk.
    from meeting_processor.audio import extract_audio
    print(">> extraindo áudio (WAV 16kHz mono)...")
    wav = extract_audio(audio, config)
    print(f"   wav: {wav}")

    print(">> rodando pyannote (pode levar alguns minutos)...")
    turns, emb = diarize(wav, config)
    print(f"   turnos     : {len(turns)}")
    print(f"   embeddings : {len(emb)} falante(s) -> {list(emb)}")

    # check 1+2: embeddings saíram e têm dimensão sensata
    if not emb:
        print("\n[FALHA] nenhum embedding. Se o modelo for o 3.1, troque para "
              "community-1 (MEETING_DIARIZATION_MODEL).")
        return 1
    dims = {k: len(v) for k, v in emb.items()}
    print(f"   dimensões  : {dims}")

    labels = list(emb)

    # check 3: mesmo falante reconhece a si mesmo (~0)
    repo: dict = {}
    voiceprints.enroll(repo, "PESSOA_A", emb[labels[0]])
    d_same = _cos(emb[labels[0]], repo["PESSOA_A"]["vector"])
    match_self = voiceprints.match(repo, emb[labels[0]], config.voice_id_threshold)
    print(f"\n[mesmo falante]  d={d_same:.4f}  match={match_self!r}  "
          f"(esperado: ~0, match='PESSOA_A')")

    # check 4: distâncias entre falantes diferentes (datapoint p/ tunar threshold)
    if len(labels) >= 2:
        print("\n[falantes diferentes] distância cosseno par-a-par:")
        worst = 1.0
        for i in range(len(labels)):
            for j in range(i + 1, len(labels)):
                d = _cos(emb[labels[i]], emb[labels[j]])
                worst = min(worst, d)
                flag = "  <-- ABAIXO do threshold (falso positivo!)" \
                    if d < config.voice_id_threshold else ""
                print(f"   {labels[i]} vs {labels[j]}: {d:.4f}{flag}")
        print(f"\n   menor distância entre pessoas distintas: {worst:.4f}")
        print(f"   threshold atual: {config.voice_id_threshold}  -> "
              f"{'OK (separa)' if worst > config.voice_id_threshold else 'APERTAR threshold'}")
    else:
        print("\n[aviso] só 1 falante detectado — sem datapoint inter-pessoa "
              "para tunar o threshold. Use uma gravação com 2+ vozes.")

    print("\nsmoke-test concluído.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
