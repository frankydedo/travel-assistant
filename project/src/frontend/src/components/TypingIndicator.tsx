import { AssistantAvatar } from "./Avatar";

export function TypingIndicator() {
  return (
    <div className="flex gap-3" role="status" aria-live="polite">
      <AssistantAvatar kind={null} />
      <div className="flex items-center gap-1 rounded-2xl rounded-tl-md border border-zinc-200 bg-white px-4 py-3.5 dark:border-zinc-800 dark:bg-zinc-900">
        {[0, 150, 300].map((delay) => (
          <span
            key={delay}
            aria-hidden
            className="size-1.5 animate-typing rounded-full bg-zinc-400 dark:bg-zinc-500"
            style={{ animationDelay: `${delay}ms` }}
          />
        ))}
        <span className="sr-only">L'assistente sta scrivendo…</span>
      </div>
    </div>
  );
}
