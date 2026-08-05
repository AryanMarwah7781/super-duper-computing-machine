import type { ConnectionState, HistoryEntry, TurnDto } from "@/lib/bridge"
import { AnswerView } from "./AnswerView"
import { AskBar } from "./AskBar"
import { CollaborationMark } from "./CollaborationMark"
import { HistorySidebar } from "./HistorySidebar"
import { ChatbotArt } from "./art/TileArt"

/** Shown until the first question — the screen should say what it is for. */
function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <ChatbotArt className="h-40 text-primary" />
      <h1 className="mt-4 text-3xl font-semibold tracking-tight">
        Let's start farming.
      </h1>
      <p className="mt-3 max-w-md text-lg text-muted-foreground">
        Ask me anything about the machine — or how to get the simulator running.
      </p>
      <CollaborationMark className="mt-10" />
    </div>
  )
}

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
  const empty = !turn && !busy

  return (
    <div className="flex h-full min-h-0">
      <HistorySidebar entries={entries} onReopen={onReopen} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* The answer takes the room; the question box waits at the bottom,
            where the hand already is. */}
        <main className="min-h-0 flex-1 overflow-y-auto">
          {empty ? <EmptyState /> : <AnswerView turn={turn} />}
        </main>

        {unavailable && (
          <div className="border-t bg-amber-100 px-6 py-3 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            {detail}
          </div>
        )}
        {error && (
          <div className="border-t bg-red-100 px-6 py-3 text-red-900 dark:bg-red-950 dark:text-red-100">
            {error}
          </div>
        )}

        <AskBar
          onAsk={onAsk}
          busy={busy}
          disabled={unavailable || state === "connecting"}
        />
      </div>
    </div>
  )
}
