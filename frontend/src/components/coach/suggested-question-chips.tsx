import { SUGGESTED_QUESTIONS } from "@/lib/coach";
import { cn } from "@/lib/utils";

export function SuggestedQuestionChips({
  onPick,
  disabled,
  className,
}: {
  onPick: (question: string) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {SUGGESTED_QUESTIONS.map((q) => (
        <button
          key={q}
          type="button"
          disabled={disabled}
          onClick={() => onPick(q)}
          className="rounded-4xl border px-3 py-1 text-sm transition-colors hover:bg-muted disabled:pointer-events-none disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
