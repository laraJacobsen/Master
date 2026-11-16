import { twMerge } from "tailwind-merge";

/**
 * Joins class names, dropping falsy entries. Conflicting Tailwind utilities
 * are resolved in favour of the later one, so a page can override a shared
 * primitive's defaults (e.g. <Card className="p-0">) and actually win.
 */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return twMerge(parts.filter(Boolean).join(" "));
}
