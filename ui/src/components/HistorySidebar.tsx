import { MessageSquare, Mic } from "lucide-react"
import { ScrollArea } from "@/components/ui/scroll-area"
import type { HistoryEntry } from "@/lib/bridge"

const KIND_LABEL: Record<string, string> = {
  cached: "Procedure",
  synthesize: "Excerpt",
  oos: "No answer",
  error: "Failed",
}

export function HistorySidebar({
  entries,
  onReopen,
}: {
  entries: HistoryEntry[]
  onReopen: (entry: HistoryEntry) => void
}) {
  return (
    <aside className="flex w-72 shrink-0 flex-col border-r">
      <h2 className="px-4 py-3 text-sm font-semibold text-muted-foreground">
        Your questions
      </h2>
      <ScrollArea className="flex-1">
        {entries.length === 0 ? (
          <p className="px-4 py-2 text-sm text-muted-foreground">
            Nothing yet. Ask something.
          </p>
        ) : (
          <ul className="space-y-1 px-2 pb-4">
            {entries.map((entry, i) => (
              <li key={`${entry.ts}-${i}`}>
                <button
                  type="button"
                  // Only a stored turn can be re-opened; older entries were
                  // recorded before the answer was kept, so they are inert.
                  disabled={!entry.turn}
                  onClick={() => onReopen(entry)}
                  className="w-full rounded-lg px-3 py-2 text-left text-sm
                             transition hover:bg-accent
                             disabled:cursor-default disabled:opacity-60
                             disabled:hover:bg-transparent"
                >
                  <span className="flex items-center gap-2">
                    {entry.source === "voice" ? (
                      <Mic className="size-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                    )}
                    <span className="truncate">{entry.query}</span>
                  </span>
                  <span className="mt-0.5 block pl-5 text-xs text-muted-foreground">
                    {KIND_LABEL[entry.kind] ?? entry.kind}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </ScrollArea>
    </aside>
  )
}
