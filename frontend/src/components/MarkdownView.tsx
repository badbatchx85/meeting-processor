import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownView({ children }: { children: string }) {
  return (
    <div
      className="prose prose-stone max-w-none prose-headings:font-display prose-headings:font-semibold prose-headings:tracking-tightest prose-headings:text-ink prose-h1:text-2xl prose-h2:text-xl prose-h2:mt-8 prose-p:text-ink-soft prose-strong:text-ink prose-a:text-ink prose-a:decoration-line prose-a:underline-offset-2 prose-li:text-ink-soft prose-blockquote:border-l-ink prose-blockquote:text-muted prose-code:font-mono prose-code:text-[0.85em] prose-pre:rounded-lg prose-pre:border prose-pre:border-line prose-pre:bg-line-soft prose-pre:text-ink"
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || "_Sem conteúdo._"}</ReactMarkdown>
    </div>
  );
}
