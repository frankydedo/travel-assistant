import { Moon, Sun } from "lucide-react";
import { useTheme } from "../theme/theme";
import { cn } from "./ui/cn";

/** Interruttore chiaro/scuro: un solo pulsante che alterna i due temi. */
export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useTheme();
  const dark = theme === "dark";
  const label = dark ? "Passa al tema chiaro" : "Passa al tema scuro";
  const Icon = dark ? Sun : Moon;

  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex size-9 shrink-0 items-center justify-center rounded-full text-zinc-600 ring-1 ring-zinc-200/70 transition-colors ring-inset hover:bg-zinc-100 hover:text-zinc-900",
        "dark:text-zinc-300 dark:ring-zinc-700/60 dark:hover:bg-zinc-800 dark:hover:text-white",
        className,
      )}
    >
      <Icon className="size-4" aria-hidden />
    </button>
  );
}
