import { AnswerView } from "@/components/AnswerView"
import { AskBar } from "@/components/AskBar"
import { StatusStrip } from "@/components/StatusStrip"
import { useAssist } from "@/hooks/useAssist"

export default function App() {
  const { state, detail, turn, error, busy, ask } = useAssist()
  const unavailable = state === "offline" || state === "warming"

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <AskBar onAsk={ask} busy={busy} disabled={unavailable} />
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
        <AnswerView turn={turn} />
      </main>
      <StatusStrip
        state={state}
        detail={detail}
        totalMs={turn?.timing?.total_ms}
      />
    </div>
  )
}
