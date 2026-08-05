import type { ConnectionState } from "@/lib/bridge"

const COLOURS: Record<ConnectionState, string> = {
  ready: "bg-green-500",
  warming: "bg-amber-500",
  connecting: "bg-amber-500",
  offline: "bg-red-500",
}

export function StatusStrip({
  state,
  detail,
  totalMs,
}: {
  state: ConnectionState
  detail: string
  totalMs?: number
}) {
  return (
    <div className="flex items-center gap-3 border-t px-6 py-2 text-sm text-muted-foreground">
      <span className={`size-2.5 rounded-full ${COLOURS[state]}`} />
      <span>{detail}</span>
      {totalMs ? (
        <span className="ml-auto tabular-nums">
          {(totalMs / 1000).toFixed(1)}s
        </span>
      ) : null}
    </div>
  )
}
