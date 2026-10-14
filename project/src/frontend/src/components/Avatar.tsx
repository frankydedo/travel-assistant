import { Bot, Cpu, ShieldCheck, Sparkles } from "lucide-react";
import { initials } from "../lib/format";
import type { Provenance } from "./Provenance";
import { cn } from "./ui/cn";

const BASE = "flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold select-none";

export function UserAvatar({ name, className }: { name: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(BASE, "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/20 dark:text-indigo-200", className)}
    >
      {initials(name)}
    </span>
  );
}

export function AssistantAvatar({ kind }: { kind: Provenance | null }) {
  if (kind === "ai") {
    return (
      <span aria-hidden className={cn(BASE, "bg-linear-to-br from-violet-500 to-indigo-600 text-white shadow-sm shadow-violet-500/30")}>
        <Sparkles className="size-4" />
      </span>
    );
  }
  if (kind === "rules") {
    return (
      <span aria-hidden className={cn(BASE, "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300")}>
        <Cpu className="size-4" />
      </span>
    );
  }
  if (kind === "system") {
    return (
      <span aria-hidden className={cn(BASE, "bg-sky-100 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300")}>
        <ShieldCheck className="size-4" />
      </span>
    );
  }
  return (
    <span aria-hidden className={cn(BASE, "bg-zinc-200 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300")}>
      <Bot className="size-4" />
    </span>
  );
}
