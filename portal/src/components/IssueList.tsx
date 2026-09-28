import { clsx } from "clsx";

interface IssueListProps {
  /** Collapsed summary text, e.g. "Warnings (315)". */
  label: string;
  items: string[];
  tone: "warning" | "error";
  testId?: string;
}

/**
 * Long lists of parser warnings/errors (an xlsx template can produce 300+)
 * collapsed behind one line, so the short headline message stays the first
 * thing the user reads.
 */
export function IssueList({ label, items, tone, testId }: IssueListProps) {
  if (items.length === 0) return null;
  return (
    <details
      data-testid={testId}
      className={clsx(
        "rounded p-3 text-xs",
        tone === "warning" ? "bg-yellow-50 text-yellow-700" : "bg-red-50 text-red-700",
      )}
    >
      <summary className="cursor-pointer font-medium">{label}</summary>
      <ul className="mt-2 max-h-64 list-inside list-disc space-y-0.5 overflow-auto">
        {items.map((item, i) => <li key={i}>{item}</li>)}
      </ul>
    </details>
  );
}
