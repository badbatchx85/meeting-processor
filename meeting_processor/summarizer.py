"""Resumo de reuniões via LLM (Claude, OpenAI, Gemini ou Ollama local).

Este módulo expõe:

- ``MeetingSummarizer``: factory pública. Retorna o provedor correto
  com base em ``config.llm_provider`` (``anthropic``, ``openai``,
  ``gemini`` ou ``local``).
- ``AnthropicSummarizer``: Claude API.
- ``OpenAISummarizer``: OpenAI e qualquer serviço compatível (OpenRouter,
  Groq, DeepSeek, xAI, Azure...) via ``openai_base_url``.
- ``GeminiSummarizer``: Google Gemini (API nativa).
- ``OllamaSummarizer``: servidor Ollama local.

Todos os provedores compartilham o mesmo system prompt e a mesma rotina de
parsing, então a saída é sempre um ``MeetingSummary`` com o mesmo formato.
"""

from __future__ import annotations

import json
import logging
import math
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
from .utils import format_duration, format_timestamp

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Você é um assistente especializado em resumir reuniões transcritas em português brasileiro.
Analise a transcrição fornecida e produza uma análise estruturada em JSON.

Responda APENAS com JSON válido, sem markdown, sem blocos de código. O JSON deve seguir esta estrutura exata:

{
  "executive_summary": "Resumo executivo de 3-5 frases",
  "purpose": "Uma frase: por que a reunião aconteceu / qual o objetivo",
  "meeting_type": "Rótulo curto do tipo de reunião (ex.: daily, 1:1, planejamento, retrospectiva, reunião com cliente, brainstorm) ou string vazia",
  "time_windows": [
    {
      "start_minutes": 0,
      "end_minutes": 5,
      "summary": "Resumo do que foi discutido neste período"
    }
  ],
  "decisions": ["Decisão tomada na reunião"],
  "action_items": [
    {
      "description": "Descrição clara da tarefa",
      "assignee": "Nome do responsável ou null",
      "priority": "alta/média/baixa ou null",
      "due_date": "Prazo mencionado ou null",
      "source_timestamp": "MM:SS aproximado de quando foi mencionada"
    }
  ],
  "open_questions": ["Questão em aberto, risco ou bloqueio levantado mas não resolvido"],
  "participants": ["Nome1", "Nome2"],
  "key_topics": ["Tópico 1", "Tópico 2"]
}

Regras:
- O resumo executivo deve capturar as decisões principais e o tom geral da reunião.
- "purpose" deve ser uma única frase com o objetivo central da reunião; use string vazia se não der para inferir.
- "meeting_type" é um rótulo curto inferido do conteúdo; use string vazia se não estiver claro.
- Cada time_window cobre um bloco de {chunk_minutes} minutos da reunião.
- "decisions" lista apenas decisões efetivamente tomadas (distintas das tarefas); use lista vazia se não houver.
- Extraia TODAS as tarefas, ações e compromissos mencionados, mesmo os implícitos.
- "open_questions" lista perguntas/riscos/bloqueios levantados e não resolvidos; use lista vazia se não houver.
- Se não conseguir identificar participantes pelo nome, use "Participante 1", etc.
- Se não houver tarefas, retorne uma lista vazia para action_items.
- Tópicos principais devem ser 3-5 temas centrais discutidos.\
"""

# Sentinela do resumo "falhou" — usada para detectar blocos que não puderam
# ser resumidos no caminho map-reduce.
_ERROR_SUMMARY = "Erro ao processar resumo da reunião."

# Estimativa de tokens: chars/_TOKEN_CHARS. Medido em PT + timestamps markdown
# (~2.5 chars/token). Conservador de propósito (superestima) para fragmentar um
# pouco antes em vez de estourar a janela de contexto.
_TOKEN_CHARS = 2.5
# Margem de segurança (tokens) reservada além do system prompt e da saída.
_BUDGET_MARGIN = 512

# System prompt do passo "reduce": combina resumos parciais em um só.
REDUCE_SYSTEM_PROMPT = """\
Você recebe vários resumos parciais de uma MESMA reunião, em ordem cronológica.
Combine-os em um único resumo coerente em português brasileiro.

Responda APENAS com JSON válido, sem markdown, sem blocos de código:

{
  "executive_summary": "Resumo executivo unificado de 3-5 frases cobrindo a reunião inteira",
  "purpose": "Uma frase com o objetivo central da reunião, ou string vazia"
}

Regras:
- Una as ideias dos trechos sem repetição; produza UM resumo executivo fluido.
- Não invente informação que não esteja nos resumos parciais.\
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

    @property
    def context_token_budget(self) -> int:
        """Tamanho efetivo da janela de contexto do provedor (em tokens).

        Padrão alto: provedores na nuvem (Claude/OpenAI/Gemini) têm janelas
        grandes e praticamente nunca precisam fragmentar. Subclasses locais
        sobrescrevem com o valor real.
        """
        return 200_000

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return math.ceil(len(text) / _TOKEN_CHARS)

    def _input_token_budget(self) -> int:
        """Tokens disponíveis para a TRANSCRIÇÃO (fora system prompt + saída)."""
        budget = (
            self.context_token_budget
            - self._estimate_tokens(SYSTEM_PROMPT)
            - self.config.max_tokens_summary
            - _BUDGET_MARGIN
        )
        return max(budget, 1000)

    # API pública -----------------------------------------------------------

    def _build_user_prompt(
        self, source_filename: str, duration: float, chunked_text: str
    ) -> str:
        return (
            f"Arquivo de origem: {source_filename}\n"
            f"Duração total: {format_duration(duration)}\n\n"
            f"--- TRANSCRIÇÃO ---\n\n{chunked_text}"
        )

    def summarize(self, transcript: Transcript, source_filename: str) -> MeetingSummary:
        chunked_text = self._build_chunked_transcript(
            transcript.segments,
            self.config.summary_chunk_minutes,
        )

        user_prompt = self._build_user_prompt(
            source_filename, transcript.duration, chunked_text
        )

        system_prompt = SYSTEM_PROMPT.replace(
            "{chunk_minutes}", str(self.config.summary_chunk_minutes)
        )

        if self._estimate_tokens(user_prompt) <= self._input_token_budget():
            logger.info(
                "Enviando transcrição ao provedor '%s' para resumo...",
                self.provider_name,
            )
            summary = self._parse_response(self._call_llm(system_prompt, user_prompt))
        else:
            summary = self._map_reduce_summarize(
                transcript, source_filename, system_prompt
            )

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

            timestamp = format_timestamp(seg.start)
            lines.append(f"  [{timestamp}] {seg.text}")

        return "\n".join(lines)

    @staticmethod
    def _split_segments(
        segments: list[TranscriptSegment], char_budget: int
    ) -> list[list[TranscriptSegment]]:
        """Agrupa segmentos sequenciais em blocos sob ``char_budget`` chars.

        Nunca divide um segmento; um segmento maior que o orçamento vira um
        bloco sozinho. ``+ 32`` por segmento aproxima o overhead do timestamp
        markdown adicionado por ``_build_chunked_transcript``.
        """
        chunks: list[list[TranscriptSegment]] = []
        current: list[TranscriptSegment] = []
        current_len = 0
        for seg in segments:
            seg_len = len(seg.text) + 32
            if current and current_len + seg_len > char_budget:
                chunks.append(current)
                current = []
                current_len = 0
            current.append(seg)
            current_len += seg_len
        if current:
            chunks.append(current)
        return chunks

    @staticmethod
    def _extract_json(response_text: str) -> dict | None:
        """Extrai um objeto JSON da resposta do LLM, ou ``None`` se não houver.

        Tolera blocos de código markdown e texto antes/depois do JSON (modelos
        locais às vezes adicionam preâmbulo). Só retorna ``dict`` — uma resposta
        que parseia para lista/escalar é tratada como ausência de objeto.
        """
        cleaned = response_text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _as_list(value) -> list:
        return value if isinstance(value, list) else []

    @staticmethod
    def _coerce_action_item(raw):
        if not isinstance(raw, dict):
            return None
        data = dict(raw)
        if isinstance(data.get("priority"), str):
            data["priority"] = data["priority"].strip().lower() or None
        try:
            return ActionItem(**data)
        except Exception:  # noqa: BLE001 — pula item malformado, mantém os bons
            logger.debug("ActionItem inválido ignorado: %s", raw)
            return None

    @staticmethod
    def _coerce_time_window(raw):
        if not isinstance(raw, dict):
            return None
        try:
            return TimeWindowSummary(
                start_minutes=int(raw.get("start_minutes", 0)),
                end_minutes=int(raw.get("end_minutes", 0)),
                summary=str(raw.get("summary", "")),
            )
        except Exception:  # noqa: BLE001
            logger.debug("TimeWindow inválido ignorado: %s", raw)
            return None

    def _parse_response(self, response_text: str) -> MeetingSummary:
        data = self._extract_json(response_text)
        if data is None:
            logger.error("Não foi possível extrair JSON da resposta do LLM.")
            logger.debug("Resposta bruta: %s", response_text[:500])
            return self._empty_summary()

        return MeetingSummary(
            executive_summary=str(data.get("executive_summary", "") or ""),
            time_windows=[
                tw for tw in (self._coerce_time_window(x) for x in self._as_list(data.get("time_windows"))) if tw
            ],
            action_items=[
                ai for ai in (self._coerce_action_item(x) for x in self._as_list(data.get("action_items"))) if ai
            ],
            participants=[str(x) for x in self._as_list(data.get("participants"))],
            key_topics=[str(x) for x in self._as_list(data.get("key_topics"))],
            purpose=str(data.get("purpose", "") or ""),
            meeting_type=str(data.get("meeting_type", "") or ""),
            decisions=[str(x) for x in self._as_list(data.get("decisions"))],
            open_questions=[str(x) for x in self._as_list(data.get("open_questions"))],
        )

    @staticmethod
    def _empty_summary() -> MeetingSummary:
        return MeetingSummary(
            executive_summary=_ERROR_SUMMARY,
            time_windows=[],
            action_items=[],
            participants=[],
            key_topics=[],
            purpose="",
            meeting_type="",
            decisions=[],
            open_questions=[],
        )

    @staticmethod
    def _dedupe_strings(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for it in items:
            key = it.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(it)
        return out

    @staticmethod
    def _dedupe_action_items(items: list[ActionItem]) -> list[ActionItem]:
        seen: set[str] = set()
        out: list[ActionItem] = []
        for ai in items:
            key = ai.description.strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(ai)
        return out

    def _reduce_narrative(self, partials: list[MeetingSummary]) -> tuple[str, str]:
        """Sintetiza executive_summary + purpose via uma chamada LLM 'reduce'.

        Em qualquer falha (sem JSON, erro de chamada), cai para a concatenação
        dos resumos parciais — nunca perde conteúdo.
        """
        fallback_summary = "\n\n".join(
            p.executive_summary for p in partials if p.executive_summary
        )
        fallback_purpose = next((p.purpose for p in partials if p.purpose), "")

        blocks = []
        for i, p in enumerate(partials, 1):
            parts = [f"[Trecho {i}] {p.executive_summary}"]
            if p.key_topics:
                parts.append("Tópicos: " + ", ".join(p.key_topics))
            if p.decisions:
                parts.append("Decisões: " + "; ".join(p.decisions))
            blocks.append("\n".join(parts))
        user_prompt = "Resumos parciais (em ordem):\n\n" + "\n\n".join(blocks)

        try:
            data = self._extract_json(self._call_llm(REDUCE_SYSTEM_PROMPT, user_prompt))
            if data is None:
                raise ValueError("reduce sem JSON")
            return (
                data.get("executive_summary") or fallback_summary,
                data.get("purpose") or fallback_purpose,
            )
        except Exception as e:  # noqa: BLE001 — degradação graciosa
            logger.warning(
                "Reduce do resumo falhou (%s); usando concatenação dos parciais.", e
            )
            return fallback_summary, fallback_purpose

    def _map_reduce_summarize(
        self, transcript: Transcript, source_filename: str, system_prompt: str
    ) -> MeetingSummary:
        """Resume uma transcrição que não cabe na janela: divide, resume cada
        bloco (map) e combina (reduce)."""
        char_budget = int(self._input_token_budget() * _TOKEN_CHARS)
        chunks = self._split_segments(transcript.segments, char_budget)
        logger.info(
            "Transcrição grande para '%s': %d segmentos em %d blocos (map-reduce).",
            self.provider_name,
            len(transcript.segments),
            len(chunks),
        )

        partials: list[MeetingSummary] = []
        for i, chunk in enumerate(chunks, 1):
            chunked_text = self._build_chunked_transcript(
                chunk, self.config.summary_chunk_minutes
            )
            user_prompt = self._build_user_prompt(
                source_filename, transcript.duration, chunked_text
            )
            logger.info("  Resumindo bloco %d/%d (%d segmentos)...", i, len(chunks), len(chunk))
            partial = self._parse_response(self._call_llm(system_prompt, user_prompt))
            if partial.executive_summary == _ERROR_SUMMARY:
                logger.warning("  Bloco %d não pôde ser resumido; ignorando.", i)
                continue
            partials.append(partial)

        return self._reduce_partials(partials)

    def _reduce_partials(self, partials: list[MeetingSummary]) -> MeetingSummary:
        """Combina resumos parciais: listas no código, narrativa via LLM."""
        if not partials:
            return self._empty_summary()

        executive_summary, purpose = self._reduce_narrative(partials)
        return MeetingSummary(
            executive_summary=executive_summary,
            time_windows=[tw for p in partials for tw in p.time_windows],
            action_items=self._dedupe_action_items(
                [ai for p in partials for ai in p.action_items]
            ),
            participants=self._dedupe_strings(
                [x for p in partials for x in p.participants]
            ),
            key_topics=self._dedupe_strings([x for p in partials for x in p.key_topics]),
            purpose=purpose,
            meeting_type=next((p.meeting_type for p in partials if p.meeting_type), ""),
            decisions=self._dedupe_strings([x for p in partials for x in p.decisions]),
            open_questions=self._dedupe_strings(
                [x for p in partials for x in p.open_questions]
            ),
        )

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

    @property
    def context_token_budget(self) -> int:
        return self.num_ctx

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
# Provedor: OpenAI e compatíveis (OpenRouter, Groq, DeepSeek, xAI, Azure...)
# ---------------------------------------------------------------------------


class OpenAISummarizer(_BaseSummarizer):
    """Resume via API compatível com a OpenAI (``/chat/completions``).

    O mesmo provedor cobre a OpenAI e qualquer serviço compatível: basta
    apontar ``openai_base_url`` e definir a chave correspondente. Assim,
    modelos novos do mercado funcionam sem mudança de código.
    """

    provider_name = "openai"

    def __init__(self, config: Settings):
        super().__init__(config)
        if not config.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY não definido. Configure no .env "
                "(ou troque o provedor de LLM)."
            )
        self.base_url = config.openai_base_url.rstrip("/")
        self.model = config.openai_model
        self.api_key = config.openai_api_key
        self.timeout = config.openai_request_timeout

    def _call_llm(self, system_prompt: str, user_prompt: str, retries: int = 3) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        use_json_mode = True
        last_err: Exception | None = None

        for attempt in range(retries):
            payload: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if use_json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    if resp.status_code == 401:
                        raise RuntimeError(
                            "Chave da API inválida (HTTP 401). "
                            "Verifique OPENAI_API_KEY no .env."
                        )
                    # Alguns endpoints compatíveis não suportam response_format.
                    if resp.status_code == 400 and use_json_mode:
                        logger.warning(
                            "Endpoint recusou response_format; tentando sem JSON mode."
                        )
                        use_json_mode = False
                        continue
                    resp.raise_for_status()
                    data = resp.json()

                choices = data.get("choices", [])
                if not choices:
                    raise RuntimeError(
                        f"Resposta inesperada da API: {str(data)[:200]}"
                    )
                return choices[0].get("message", {}).get("content", "")

            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"Não foi possível conectar a {self.base_url}. "
                    f"Verifique openai_base_url."
                ) from e
            except httpx.HTTPError as e:
                last_err = e
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Erro HTTP na API OpenAI (%s). Tentando novamente em %ds...",
                        e,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Falha ao chamar a API OpenAI após {retries} tentativas: {e}"
                    ) from e

        raise RuntimeError(f"Falha ao chamar a API OpenAI: {last_err}")


# ---------------------------------------------------------------------------
# Provedor: Google Gemini (API nativa)
# ---------------------------------------------------------------------------


class GeminiSummarizer(_BaseSummarizer):
    """Resume via API nativa do Google Gemini (``generateContent``)."""

    provider_name = "gemini"

    def __init__(self, config: Settings):
        super().__init__(config)
        if not config.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY não definido. Configure no .env "
                "(ou troque o provedor de LLM)."
            )
        self.base_url = config.gemini_base_url.rstrip("/")
        self.model = config.gemini_model
        self.api_key = config.gemini_api_key
        self.timeout = config.gemini_request_timeout

    def _call_llm(self, system_prompt: str, user_prompt: str, retries: int = 3) -> str:
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
        last_err: Exception | None = None

        for attempt in range(retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(
                        url, params={"key": self.api_key}, json=payload
                    )
                    if resp.status_code in (401, 403):
                        raise RuntimeError(
                            "Chave da API Gemini inválida. "
                            "Verifique GEMINI_API_KEY no .env."
                        )
                    if resp.status_code == 404:
                        raise RuntimeError(
                            f"Modelo Gemini '{self.model}' não encontrado (HTTP 404). "
                            f"Confira gemini_model."
                        )
                    resp.raise_for_status()
                    data = resp.json()

                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(
                        f"Resposta inesperada do Gemini: {str(data)[:200]}"
                    )
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
                if not text:
                    raise RuntimeError(
                        f"Gemini não retornou texto: {str(data)[:200]}"
                    )
                return text

            except httpx.ConnectError as e:
                raise RuntimeError(
                    f"Não foi possível conectar ao Gemini em {self.base_url}."
                ) from e
            except httpx.HTTPError as e:
                last_err = e
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Erro HTTP no Gemini (%s). Tentando novamente em %ds...",
                        e,
                        wait,
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Falha ao chamar o Gemini após {retries} tentativas: {e}"
                    ) from e

        raise RuntimeError(f"Falha ao chamar o Gemini: {last_err}")


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

    if provider == "none":
        raise RuntimeError(
            "llm_provider='none' não usa LLM (modo só transcrição). "
            "O resumo não deveria ter sido chamado."
        )

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

    if provider == "openai":
        logger.info(
            "LLM provider: openai (modelo=%s, base_url=%s)",
            config.openai_model,
            config.openai_base_url,
        )
        return OpenAISummarizer(config)

    if provider == "gemini":
        logger.info("LLM provider: gemini (modelo=%s)", config.gemini_model)
        return GeminiSummarizer(config)

    raise ValueError(
        f"llm_provider desconhecido: '{provider}'. Valores válidos: "
        f"'anthropic', 'openai', 'gemini', 'local' (alias 'ollama')."
    )


__all__ = [
    "MeetingSummarizer",
    "AnthropicSummarizer",
    "OpenAISummarizer",
    "GeminiSummarizer",
    "OllamaSummarizer",
    "SummarizerProtocol",
    "SYSTEM_PROMPT",
    "REDUCE_SYSTEM_PROMPT",
]
