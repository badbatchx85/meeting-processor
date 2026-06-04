import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function MarkdownView({ children }: { children: string }) {
  return (
    <div className="prose prose-slate max-w-none prose-headings:font-semibold prose-pre:bg-slate-100">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children || "_Sem conteúdo._"}</ReactMarkdown>
    </div>
  );
}
