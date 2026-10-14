import { forwardRef, useImperativeHandle, useLayoutEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import { SendHorizontal } from "lucide-react";
import { Button } from "./ui/Button";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

const MAX_HEIGHT = 200;

/** Composer con textarea che cresce col testo. Invio invia, Maiusc+Invio va a capo. */
export const Composer = forwardRef<HTMLTextAreaElement, Props>(function Composer(
  { value, onChange, onSubmit, disabled },
  ref,
) {
  const inner = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => inner.current as HTMLTextAreaElement);

  useLayoutEffect(() => {
    const el = inner.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [value]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onSubmit();
    }
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm transition-shadow focus-within:border-indigo-300 focus-within:ring-4 focus-within:ring-indigo-500/10 dark:border-zinc-700 dark:bg-zinc-900 dark:focus-within:border-indigo-500/50"
    >
      <label htmlFor="composer" className="sr-only">
        Messaggio
      </label>
      <textarea
        id="composer"
        ref={inner}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Scrivi un messaggio…"
        rows={1}
        disabled={disabled}
        className="max-h-[200px] min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 outline-none placeholder:text-zinc-400 focus-visible:outline-none disabled:opacity-60 dark:placeholder:text-zinc-500"
      />
      <Button
        type="submit"
        size="icon"
        className="size-10 rounded-xl"
        disabled={disabled || !value.trim()}
        aria-label="Invia messaggio"
        icon={<SendHorizontal className="size-4" aria-hidden />}
      />
    </form>
  );
});
