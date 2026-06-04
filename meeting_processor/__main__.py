"""Ponto de entrada do Meeting Processor.

Uso:
    python -m meeting_processor watch              Monitora pasta OBS (padrão)
    python -m meeting_processor process <file>     Processa um arquivo específico
    python -m meeting_processor serve              Watcher + servidor de controle
    python -m meeting_processor web [--port 8765]  Frontend local no navegador
"""

import argparse
import logging
import sys
from pathlib import Path

from .config import load_config


def setup_logging(level: str) -> None:
    """Configura logging para console e arquivo."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("meeting_processor.log", encoding="utf-8"),
    ]

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Meeting Processor - Transcreve e resume reunioes gravadas",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("watch", help="Monitora pasta do OBS")
    subparsers.add_parser(
        "serve", help="Watcher + servidor de controle (com botoes no dashboard)"
    )

    process_parser = subparsers.add_parser("process", help="Processa um arquivo de video")
    process_parser.add_argument("file", type=str, help="Caminho do arquivo de video")
    process_parser.add_argument(
        "--only-transcribe",
        action="store_true",
        help="So transcreve (sem resumo, nota, kanban ou wiki)",
    )
    process_parser.add_argument("--no-summary", action="store_true", help="Nao gera resumo (LLM)")
    process_parser.add_argument("--no-note", action="store_true", help="Nao gera nota de resumo")
    process_parser.add_argument("--no-kanban", action="store_true", help="Nao cria Kanban")
    process_parser.add_argument("--no-wiki", action="store_true", help="Nao integra com a wiki")

    web_parser = subparsers.add_parser("web", help="Frontend local no navegador")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)
    web_parser.add_argument("--reload", action="store_true", help="Auto-reload (dev)")

    args = parser.parse_args()
    config = load_config()
    setup_logging(config.log_level)

    logger = logging.getLogger(__name__)

    if args.command == "process":
        video_path = Path(args.file)
        if not video_path.exists():
            logger.error("Arquivo nao encontrado: %s", video_path)
            sys.exit(1)

        # Flags de etapa sobrescrevem a config só nesta execução.
        if args.only_transcribe or args.no_summary:
            config.enable_summary = False
        if args.no_note:
            config.enable_note = False
        if args.no_kanban:
            config.enable_kanban = False
        if args.no_wiki:
            config.enable_wiki = False

        from .pipeline import MeetingPipeline

        pipeline = MeetingPipeline(config)
        try:
            result = pipeline.process(video_path)
            print("\nProcessamento concluido!")
            print(f"  Transcricao: {result.raw_path}")
            if result.note_path:
                print(f"  Nota: {result.note_path}")
            if result.summary is not None:
                print(f"  Tarefas: {len(result.summary.action_items)}")
            print(f"  Tempo: {result.processing_time:.1f}s")
        except Exception:
            logger.exception("Erro fatal ao processar arquivo")
            sys.exit(1)

    elif args.command == "serve":
        from .control_server import start_control_server
        from .watcher import start_watching

        logger.info("Meeting Processor iniciado com servidor de controle.")
        start_control_server(config)
        start_watching(config)

    elif args.command == "web":
        from .web import run as run_web

        logger.info(
            "Iniciando frontend local em http://%s:%d (LLM: %s)",
            args.host,
            args.port,
            config.llm_provider,
        )
        run_web(host=args.host, port=args.port, reload=args.reload)

    else:
        # Padrão: modo watch
        from .watcher import start_watching

        logger.info("Meeting Processor iniciado em modo monitoramento.")
        start_watching(config)


if __name__ == "__main__":
    main()
