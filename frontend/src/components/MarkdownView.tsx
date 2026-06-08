import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// Obsidian wikilinks (`[[Target|Alias]]` / `[[Target]]`) are not standard
// Markdown, so react-markdown would render the raw `[[…]]` syntax verbatim.
// These notes don't exist as web routes, so we flatten each link to its
// human-readable text: the alias when present, otherwise the target.
export function stripWikilinks(md: string): string {
  return md.replace(/\[\[([^\]]+?)\]\]/g, (_, inner: string) => {
    const parts = inner.split("|");
    return (parts[parts.length - 1] ?? inner).trim();
  });
}

export function MarkdownView({ children }: { children: string }) {
  return (
    <div
      className="prose prose-stone max-w-none prose-headings:font-display prose-headings:font-semibold prose-headings:tracking-tightest prose-headings:text-ink prose-h1:text-2xl prose-h2:text-xl prose-h2:mt-8 prose-p:text-ink-soft prose-strong:text-ink prose-a:text-ink prose-a:decoration-line prose-a:underline-offset-2 prose-li:text-ink-soft prose-blockquote:border-l-ink prose-blockquote:text-muted prose-code:font-mono prose-code:text-[0.85em] prose-pre:rounded-lg prose-pre:border prose-pre:border-line prose-pre:bg-line-soft prose-pre:text-ink"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {stripWikilinks(children || "_Sem conteúdo._")}
      </ReactMarkdown>
    </div>
  );
}
