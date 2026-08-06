import { useEffect, useRef } from "react"
import type { ChatMessage } from "@/hooks/useAssist"
import type { ConnectionState, HistoryEntry } from "@/lib/bridge"
import { AnswerView } from "./AnswerView"
import { AskBar } from "./AskBar"
import { CollaborationMark } from "./CollaborationMark"
import { HistorySidebar } from "./HistorySidebar"
import { FarmingHeroArt } from "./art/TileArt"

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <FarmingHeroArt className="h-48 text-primary" />
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

function Question({ text }: { text: string }) {
  return (
    <div className="mx-auto flex max-w-3xl justify-end px-6 pt-8">
      <p className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-5 py-3
                    text-lg text-primary-foreground">
        {text}
      </p>
    </div>
  )
}

export function ChatScreen({
  messages,
  entries,
  busy,
  unavailable,
  detail,
  state,
  onAsk,
  onReopen,
}: {
  messages: ChatMessage[]
  entries: HistoryEntry[]
  busy: boolean
  unavailable: boolean
  detail: string
  state: ConnectionState
  onAsk: (q: string) => void
  onReopen: (entry: HistoryEntry) => void
}) {
  const end = useRef<HTMLDivElement>(null)

  // Follow the conversation as it grows, so the newest answer is on screen
  // without scrolling. Optional-called: jsdom has no scrollIntoView.
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" })
  }, [messages.length, busy])

  return (
    <div className="flex h-full min-h-0">
      <HistorySidebar entries={entries} onReopen={onReopen} />

      <div className="flex min-w-0 flex-1 flex-col">
        <main className="min-h-0 flex-1 overflow-y-auto">
          {messages.length === 0 && !busy ? (
            <EmptyState />
          ) : (
            <>
              {messages.map((m) =>
                m.role === "user" ? (
                  <Question key={m.id} text={m.text} />
                ) : m.error ? (
                  <p key={m.id} className="mx-auto max-w-3xl px-6 py-4 text-destructive">
                    {m.error}
                  </p>
                ) : (
                  <AnswerView key={m.id} turn={m.turn} />
                ),
              )}
              {busy && (
                <p className="mx-auto max-w-3xl px-6 py-6 text-muted-foreground">
                  Looking it up…
                </p>
              )}
              <div ref={end} />
            </>
          )}
        </main>

        {unavailable && (
          <div className="border-t bg-amber-100 px-6 py-3 text-amber-900 dark:bg-amber-950 dark:text-amber-100">
            {detail}
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
