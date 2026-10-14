import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Markdown dell'assistente, con un sottoinsieme ristretto e sicuro.
 * Il testo arriva da un LLM, quindi va trattato come non fidato:
 * - niente HTML grezzo (`skipHtml`);
 * - niente link né immagini: un modello manipolato via prompt injection potrebbe portare ovunque,
 *   quindi il loro testo resta come testo semplice (`unwrapDisallowed`);
 * - niente titoli né tabelle, che in una bolla di chat non servono.
 */
const ALLOWED = ["p", "strong", "em", "del", "ul", "ol", "li", "code", "pre", "blockquote", "br", "hr"];

const components: Components = {
  p: ({ children }) => <p className="my-0 [&+*]:mt-2">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5 marker:text-indigo-400">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-indigo-400">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-zinc-900 dark:text-white">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  code: ({ children }) => (
    <code className="rounded bg-zinc-900/5 px-1 py-0.5 font-mono text-[0.9em] dark:bg-white/10">{children}</code>
  ),
  pre: ({ children }) => <pre className="my-2 overflow-x-auto rounded-lg bg-zinc-900/5 p-3 dark:bg-white/10">{children}</pre>,
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-indigo-300 pl-3 text-zinc-600 dark:border-indigo-500/60 dark:text-zinc-300">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-zinc-200 dark:border-zinc-700" />,
};

export function Markdown({ text }: { text: string }) {
  return (
    <div className="break-words [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml allowedElements={ALLOWED} unwrapDisallowed components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
