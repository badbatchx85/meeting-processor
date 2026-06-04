"""Teste do pipeline completo (sem Whisper - usa transcrição simulada).

Testa: Claude API (resumo real) + Nota Obsidian + Kanban + Wiki Integration.

Uso:
    python test_pipeline.py
"""

import time
from datetime import datetime

from meeting_processor.config import load_config
from meeting_processor.kanban import KanbanManager
from meeting_processor.models import ActionItem, MeetingSummary, Transcript, TranscriptSegment
from meeting_processor.note_generator import NoteGenerator
from meeting_processor.summarizer import MeetingSummarizer
from meeting_processor.wiki_integrator import WikiIntegrator

# Transcrição simulada de uma reunião em português
MOCK_SEGMENTS = [
    (0.0, 3.5, "Bom dia a todos, vamos comecar a reuniao de alinhamento semanal."),
    (3.5, 8.0, "Hoje temos tres pontos na pauta: status do projeto Alpha, planejamento do sprint e definicao de responsaveis."),
    (8.0, 15.0, "Comecando pelo projeto Alpha. Joao, pode nos dar uma atualizacao?"),
    (15.0, 25.0, "Claro. O projeto Alpha esta com setenta por cento do backend concluido. Falta integrar a API de pagamentos e finalizar os testes."),
    (25.0, 35.0, "A integracao com a API de pagamentos esta prevista para ser concluida ate sexta-feira desta semana."),
    (35.0, 45.0, "Os testes unitarios estao em oitenta por cento. Precisamos que a Maria ajude com os testes de integracao."),
    (45.0, 55.0, "Maria, voce consegue pegar os testes de integracao a partir de amanha?"),
    (55.0, 65.0, "Sim, consigo. Vou precisar de acesso ao ambiente de staging. Pedro, voce pode liberar?"),
    (65.0, 75.0, "Libero hoje a tarde. Vou configurar as credenciais e te enviar por email."),
    (75.0, 90.0, "Otimo. Segundo ponto: planejamento do sprint. Temos que priorizar a correcao do bug critico no modulo de relatorios."),
    (90.0, 105.0, "O bug esta causando dados incorretos nos relatorios financeiros dos clientes. Prioridade maxima."),
    (105.0, 120.0, "Joao, voce consegue olhar esse bug ate quarta-feira? E o mais urgente agora."),
    (120.0, 135.0, "Consigo sim. Vou comecar a investigar hoje depois do almoco."),
    (135.0, 150.0, "Perfeito. Ultimo ponto: precisamos preparar a apresentacao para o cliente na proxima terca-feira."),
    (150.0, 165.0, "Maria, voce fica responsavel pela apresentacao. Joao prepara os dados tecnicos e Pedro monta o ambiente de demo."),
    (165.0, 180.0, "Combinado. Vou criar o deck no PowerPoint e compartilhar o rascunho ate segunda para revisao."),
    (180.0, 195.0, "Pedro, a demo precisa estar funcionando no ambiente de staging ate segunda tambem."),
    (195.0, 210.0, "Sem problema. Vou garantir que o ambiente esteja estavel e com dados de teste realistas."),
    (210.0, 225.0, "Alguma duvida ou ponto adicional? Nao? Entao encerramos por aqui. Obrigado a todos."),
    (225.0, 230.0, "Obrigado. Ate a proxima."),
]


def main():
    config = load_config()

    # 1. Montar transcrição simulada
    print("=" * 60)
    print("TESTE DO PIPELINE - Meeting Processor")
    print("=" * 60)

    segments = [
        TranscriptSegment(start=s, end=e, text=t)
        for s, e, t in MOCK_SEGMENTS
    ]

    transcript = Transcript(
        segments=segments,
        full_text=" ".join(seg.text for seg in segments),
        language="pt",
        duration=segments[-1].end,
    )

    print(f"\nTranscricao simulada: {len(segments)} segmentos, {transcript.duration/60:.1f} minutos")

    # 2. Resumir com Claude API (chamada REAL)
    print("\n[1/4] Enviando para Claude API...")
    start = time.time()
    summarizer = MeetingSummarizer(config)
    summary = summarizer.summarize(transcript, "teste-reuniao.mkv")
    elapsed_api = time.time() - start

    print(f"  Resumo gerado em {elapsed_api:.1f}s")
    print(f"  Resumo executivo: {summary.executive_summary[:100]}...")
    print(f"  Janelas de tempo: {len(summary.time_windows)}")
    print(f"  Tarefas encontradas: {len(summary.action_items)}")
    print(f"  Participantes: {summary.participants}")
    print(f"  Topicos: {summary.key_topics}")

    # 3. Gerar nota no Obsidian
    print("\n[2/4] Gerando nota de reuniao...")
    note_gen = NoteGenerator(config)
    note_path, raw_path = note_gen.generate(
        transcript=transcript,
        summary=summary,
        source_file="teste-reuniao.mkv",
        created_at=datetime.now(),
    )
    print(f"  Nota: {note_path}")
    print(f"  Transcricao bruta: {raw_path}")

    # 4. Atualizar Kanban
    print("\n[3/4] Atualizando quadro Kanban...")
    kanban = KanbanManager(config)
    title = note_path.stem
    kanban.add_tasks(
        tasks=summary.action_items,
        meeting_title=title,
        meeting_date=datetime.now().strftime("%Y-%m-%d"),
    )
    print(f"  Kanban: {config.kanban_path}")

    # 5. Integrar com wiki
    print("\n[4/4] Integrando com wiki...")
    wiki = WikiIntegrator(config)
    wiki.register_meeting(
        title=title,
        date_str=datetime.now().strftime("%Y-%m-%d"),
        source_file="teste-reuniao.mkv",
        duration=f"{int(transcript.duration//60):02d}:{int(transcript.duration%60):02d}",
        task_count=len(summary.action_items),
        key_topics=summary.key_topics,
    )

    # Resultado
    print("\n" + "=" * 60)
    print("TESTE CONCLUIDO COM SUCESSO!")
    print("=" * 60)
    print(f"\nAbra o vault em Obsidian: {config.vault_path}")
    print(f"  Nota da reuniao:  wiki/meetings/{note_path.name}")
    print(f"  Quadro Kanban:    wiki/kanban-reunioes.md")
    print(f"  Transcricao:      .raw/transcriptions/{raw_path.name}")


if __name__ == "__main__":
    main()
