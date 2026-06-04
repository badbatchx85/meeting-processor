"""Resumo de reuniões via LLM (Claude API ou modelo local Ollama).

Este módulo expõe:

- ``MeetingSummarizer``: factory pública. Retorna o provedor correto
  com base em ``config.llm_provider`` (``anthropic`` ou ``local``).
- ``AnthropicSummarizer``: provedor que chama a Claude API.
- ``OllamaSummarizer``: provedor que chama um servidor Ollama local.

Os dois provedores compartilham o mesmo system prompt e a mesma rotina de
parsing, então a saída é sempre um ``MeetingSummary`` com o mesmo formato.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

import anthropic
import httpx

from .config import Settings
from .models import (
    ActionItem,
    MeetingSummary,
    TimeWindowSummary,
    Transcript,
    TranscriptSegment,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você é um assistente especializado em resumir reuniões transcritas em português brasileiro.
Analise a transcrição fornecida e produza uma análise estruturada em JSON.

Responda APENAS com JSON válido, sem markdown, sem blocos de código. O JSON deve seguir esta estrutura exata:

{
  "executive_summary": "Resumo executivo de 3-5 frases",
  "time_windows": [
    {
      "start_minutes": 0,
      "end_minutes": 5,
      "summary": "Resumo do que foi discutido neste período"
    }
  ],
  "action_items": [
    {
      "description": "Descrição clara da tarefa",
      "assignee": "Nome do responsável ou null",
      "priority": "alta/média/baixa ou null",
      "due_date": "Prazo mencionado ou null",
      "source_timestamp": "MM:SS aproximado de quando foi mencionada"
    }
  ],
  "participants": ["Nome1", "Nome2"],
  "key_topics": ["Tópico 1", "Tópico 2"]
}

Regras:
- O resumo executivo deve capturar as decisões principais e o tom geral da reunião.
- Cada time_window cobre um bloco de {chunk_minutes} minutos da reunião.
- Extraia TODAS as tarefas, ações e compromissos mencionados, mesmo os implícitos.
- Se não conseguir identificar participantes pelo nome, use "Participante 1", etc.
- Se não houver tarefas, retorne uma lista vazia para action_items.
- Tópicos principais devem ser 3-5 temas centrais discutidos.\
"""


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class SummarizerProtocol(Protocol):
    """Interface comum entre os provedores de LLM."""

    def summarize(self, transcript: Transcript, source_filename: str) -> MeetingSummary:
        ...


# ---------------------------------------------------------------------------
# Base com lógica compartilhada
# ---------------------------------------------------------------------------


class _BaseSummarizer:
    """Implementa a montagem do prompt e o parsing do JSON.

    Subclasses devem implementar ``_call_llm(system_prompt, user_prompt)``
    retornando uma string com a resposta do modelo.
    """

    provider_name: str = "base"

    def __init__(self, config: Settings):
        self.config = config

    # API pública -----------------------------------------------------------

    def summarize(self, transcript: Transcript, source_filename: str) -> MeetingSummary:
        chunked_text = self._build_chunked_transcript(
            transcript.segments,
            self.config.summary_chunk_minutes,
        )

        user_prompt = (
            f"Arquivo de origem: {source_filename}\n"
            f"Duração total: {self._format_duration(transcript.duration)}\n\n"
            f"--- TRANSCRIÇÃO ---\n\n{chunked_text}"
        )

        system_prompt = SYSTEM_PROMPT.replace(
            "{chunk_minutes}", str(self.config.summary_chunk_minutes)
        )

        logger.info(
            "Enviando transcrição ao provedor '%s' para resumo...", self.provider_name
        )
        response_text = self._call_llm(system_prompt, user_prompt)
        summary = self._parse_response(response_text)

        logger.info(
            "Resumo gerado (%s): %d janelas, %d tarefas, %d participantes.",
            self.provider_name,
            len(summary.time_windows),
            len(summary.action_items),
            len(summary.participants),
        )
        return summary

    # Hook que cada provedor implementa -----------------------------------

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError

    # Helpers compartilhados ----------------------------------------------

    def _build_chunked_transcript(
        self,
        segments: list[TranscriptSegment],
        chunk_minutes: int,
    ) -> str:
        if not segments:
            return "(Transcrição vazia)"

        lines: list[str] = []
        current_chunk_start = 0
        chunk_seconds = chunk_minutes * 60

        for seg in segments:
            chunk_index = int(seg.start // chunk_seconds)
            chunk_start = chunk_index * chunk_minutes
            chunk_end = chunk_start + chunk_minutes

            if chunk_start != current_chunk_start or seg is segments[0]:
                current_chunk_start = chunk_start
                lines.append(f"\n[{chunk_start:02d}:00 - {chunk_end:02d}:00]")

            timestamp = self._format_timestamp(seg.start)
            lines.append(f"  [{timestamp}] {seg.text}")

        return "\n".join(lines)

    def _parse_response(self, response_text: str) -> MeetingSummary:
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        # Modelos locais às vezes adicionam texto antes/depois do JSON.
        # Se o JSON direto falhar, tenta extrair o primeiro objeto {...}.
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError as e:
                    logger.error("Resposta do LLM não é JSON válido: %s", e)
                    logger.debug("Resposta bruta: %s", response_text[:500])
                    return self._empty_summary()
            else:
                logger.error("Não foi possível extrair JSON da resposta do LLM.")
                logger.debug("Resposta bruta: %s", response_text[:500])
                return self._empty_summary()

        return MeetingSummary(
            executive_summary=data.get("executive_summary", ""),
            time_windows=[
                TimeWindowSummary(**tw) for tw in data.get("time_windows", [])
            ],
            action_items=[ActionItem(**ai) for ai in data.get("action_items", [])],
            participants=data.get("participants", []),
            key_topics=data.get("key_topics", []),
        )

    @staticmethod
    def _empty_summary() -> MeetingSummary:
        return MeetingSummary(
            executive_summary="Erro ao processar resumo da reunião.",
            time_windows=[],
            action_items=[],
            participants=[],
            key_topics=[],
        )

    @staticmethod
    def _format_duration(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Provedor: Claude (Anthropic API)
# ---------------------------------------------------------------------------


class AnthropicSummarizer(_BaseSummarizer):
    """Resume reuniões usando a Claude API."""

    provider_name = "anthropic"

    def __init__(self, config: Settings):
        super().__init__(config)
        if not config.anthropic_api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY não definido. Configure no .env ou troque "
                "o provedor para 'local' (export MEETING_LLM_PROVIDER=local)."
            )
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def _call_llm(self, system_prompt: str, user_prompt: str, retries: int = 3) -> str:
        for attempt in range(retries):
            try:
                message = self.client.messages.create(
                    model=self.config.anthropic_model,
                    max_tokens=self.config.max_tokens_summary,
                    system=[
                        {
                            "type": "text",
                            "text": system_prompt,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return message.content[0].text

            except anthropic.RateLimitError:
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning("Rate limit atingido. Aguardando %ds...", wait)
                    time.sleep(wait)
                else:
                    raise
            except anthropic.AuthenticationError as e:
                raise RuntimeError(
                    "Chave da API Anthropic inválida. "
                    "Verifique o arquivo .env com ANTHROPIC_API_KEY."
                ) from e

        raise RuntimeError("Falha ao chamar API Anthropic após todas as tentativas.")


# ---------------------------------------------------------------------------
# Provedor: Ollama (LLM local)
# ---------------------------------------------------------------------------


class OllamaSummarizer(_BaseSummarizer):
    """Resume reuniões usando um servidor Ollama local.

    Requer o Ollama instalado e rodando. Veja ``docs/llm-local.md``.

    Endpoint usado: ``POST {base_url}/api/chat`` com ``format: "json"`` para
    forçar saída em JSON estruturado, e ``stream: false`` para resposta única.
    """

    provider_name = "ollama"

    def __init__(self, config: Settings):
        super().__init__(config)
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model = config.ollama_model
        self.timeout = config.ollama_request_timeout
        self.temperature = config.ollama_temperature
        self.num_ctx = config.ollama_num_ctx

    def _call_llm(self, system_prompt: str, user_prompt: str, retries: int = 2) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "stream": False,
            # Força saída em JSON. qwen2.5/llama3.1 respeitam isso.
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
                "num_predict": self.config.max_tokens_summary,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    logger.debug(
                        "Chamando Ollama %s (modelo=%s, num_ctx=%d)",
                        url,
                        self.model,
                        self.num_ctx,
                    )
                    response = client.post(url, json=payload)
                    if response.status_code == 404:
                        raise RuntimeError(
                            f"Ollama respondeu 404. Verifique se o modelo "
                            f"'{self.model}' está instalado: "
                            f"`ollama pull {self.model}`."
                        )
                    response.raise_for_status()
                    data = response.json()

                # /api/chat retorna {"message": {"content": "..."}, ...}
                message = data.get("message", {})
                content = message.get("content")
                if not content:
                    raise RuntimeError(
                        f"Resposta inesperada do Ollama: {str(data)[:200]}"
                    )
                return content

            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"Não foi possível conectar ao Ollama em {self.base_url}. "
                    f"Verifique se o serviço está rodando "
                    f"(`ollama serve` ou app do Ollama aberto)."
                ) from e
            except httpx.HTTPError as e:
                last_err = e
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Erro HTTP no Ollama (%s). Tentando novamente em %ds...",
                        e,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Falha ao chamar Ollama após {retries} tentativas: {e}"
                    ) from e

        raise RuntimeError(f"Falha ao chamar Ollama: {last_err}")


# ---------------------------------------------------------------------------
# Factory pública
# ---------------------------------------------------------------------------


def MeetingSummarizer(config: Settings) -> SummarizerProtocol:  # noqa: N802 (factory mantém nome legado)
    """Cria o summarizer apropriado conforme ``config.llm_provider``.

    Mantém o nome ``MeetingSummarizer`` por compatibilidade com o código
    existente (``pipeline.py``, ``test_pipeline.py``). Apesar de parecer uma
    classe, é uma função factory que retorna a instância concreta.
    """
    provider = (config.llm_provider or "anthropic").lower().strip()

    if provider in ("local", "ollama"):
        logger.info(
            "LLM provider: ollama (modelo=%s, base_url=%s)",
            config.ollama_model,
            config.ollama_base_url,
        )
        return OllamaSummarizer(config)

    if provider == "anthropic":
        logger.info("LLM provider: anthropic (modelo=%s)", config.anthropic_model)
        return AnthropicSummarizer(config)

    raise ValueError(
        f"llm_provider desconhecido: '{provider}'. "
        f"Valores válidos: 'anthropic', 'local' (alias 'ollama')."
    )


__all__ = [
    "MeetingSummarizer",
    "AnthropicSummarizer",
    "OllamaSummarizer",
    "SummarizerProtocol",
    "SYSTEM_PROMPT",
]
