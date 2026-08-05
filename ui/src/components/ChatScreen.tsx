import type { HistoryEntry, TurnDto, ConnectionState } from "@/lib/bridge"
import { AnswerView } from "./AnswerView"
import { AskBar } from "./AskBar"
import { HistorySidebar } from "./HistorySidebar"

export function ChatScreen({
  turn,
  entries,
  busy,
  unavailable,
  detail,
  error,
  state,
  onAsk,
  onReopen,
}: {
  turn: TurnDto | null
  entries: HistoryEntry[]
  busy: boolean
  unavailable: boolean
  detail: string
  error: string | null
  state: ConnectionState
  onAsk: (q: string) => void
  onReopen: (entry: HistoryEntry) => void
}) {
  return (
    <div className="flex h-full min-h-0">
      <HistorySidebar entries={entries} onReopen={onReopen} />
      <div className="flex min-w-0 flex-1 flex-col">
        <AskBar onAsk={onAsk} busy={busy} disabled={unavailable} />
        {unavailable && (
          <div className="bg-amber-100 px-6 py-3 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            {detail}
          </div>
        )}
        {error && (
          <div className="bg-red-100 px-6 py-3 text-red-900 dark:bg-red-950 dark:text-red-100">
            {error}
          </div>
        )}
        <main className="flex-1 overflow-y-auto">
          {!turn && !busy && state === "ready" && (
            <p className="px-6 py-16 text-center text-muted-foreground">
              Ask a question to get started.
            </p>
          )}
          <AnswerView turn={turn} />
        </main>
      </div>
    </div>
  )
}
