import { cn } from "./cn";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-lg bg-zinc-200/80 dark:bg-zinc-800", className)} />;
}
