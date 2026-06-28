import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Search as SearchIcon, RefreshCw } from "lucide-react";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { EmptyState } from "../components/EmptyState";
import { useToast } from "../components/Toast";
import { useSearch, useReindexSearch } from "../hooks/useApi";
import { ApiError } from "../api/client";

function snippetHref(meetingId: string, start: number): string {
  return `/meetings/${encodeURIComponent(meetingId)}?t=${Math.floor(start)}`;
}

export function Search() {
  const [q, setQ] = useState("");
  const search = useSearch();
  const reindex = useReindexSearch();
  const toast = useToast();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const term = q.trim();
    if (!term) return;
    search.mutate(term, {
      onError: (err) => toast("err", err instanceof ApiError ? err.message : "Erro na busca"),
    });
  };

  const runReindex = () =>
    reindex.mutate(undefined, {
      onSuccess: (d) => toast("ok", `Reindexado: ${d.indexed} reuniõe(s).`),
      onError: (err) => toast("err", err instanceof ApiError ? err.message : "Erro ao reindexar"),
    });

  const results = search.data?.results ?? [];
  const searched = search.isSuccess || search.isError;

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        index="05"
        eyebrow="Busca"
        title="Busca semântica"
        description="Encontre trechos por tema ou pergunta — sem precisar das palavras exatas."
        actions={
          <button
            onClick={runReindex}
            disabled={reindex.isPending}
            title="Reindexar todas as reuniões"
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-[13px] font-medium text-muted transition-colors hover:border-ink hover:text-ink disabled:opacity-40"
          >
            <RefreshCw size={14} className={reindex.isPending ? "animate-spin" : ""} />
            {reindex.isPending ? "Reindexando…" : "Reindexar"}
          </button>
        }
      />

      <Card>
        <form role="search" onSubmit={submit} className="flex items-center gap-2">
          <label className="flex flex-1 items-center gap-2 rounded-lg border border-line bg-surface px-3 focus-within:border-ink">
            <SearchIcon size={15} className="text-muted-soft" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por tema, decisão, pergunta…"
              className="w-full bg-transparent py-2.5 text-sm outline-none placeholder:text-muted-soft"
            />
          </label>
          <button
            type="submit"
            disabled={search.isPending || !q.trim()}
            className="rounded-lg border border-line px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:border-ink hover:bg-ink hover:text-paper disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-ink"
          >
            {search.isPending ? "Buscando…" : "Buscar"}
          </button>
        </form>

        <div className="mt-6">
          {results.length > 0 ? (
            <ul className="flex flex-col divide-y divide-line-soft">
              {results.map((r, i) => (
                <li key={`${r.meeting_id}-${i}`} className="py-4 first:pt-0">
                  <p className="text-sm leading-7 text-ink-soft">{r.text}</p>
                  <div className="mt-1.5 flex items-center gap-3 text-xs">
                    <Link
                      to={snippetHref(r.meeting_id, r.start)}
                      className="font-medium text-brand hover:underline"
                    >
                      {r.meeting_id}
                    </Link>
                    <span className="font-mono tabular-nums text-muted-soft">
                      {Math.round(r.score * 100)}%
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          ) : searched && !search.isPending ? (
            <EmptyState title="Nada encontrado" hint="Tente outros termos ou reindexe as reuniões." />
          ) : null}
        </div>
      </Card>
    </div>
  );
}
