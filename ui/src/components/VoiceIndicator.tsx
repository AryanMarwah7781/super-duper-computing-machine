import { Mic, MicOff, Loader2 } from "lucide-react"
import type { VoiceState } from "@/hooks/useAssist"

/**
 * What the microphone is doing, at a glance.
 *
 * The level meter matters more than it looks: it is the only way an operator
 * can tell a live microphone from a dead one before they start talking. A
 * still bar means the audio path is broken, not that the room is quiet.
 */
export function VoiceIndicator({
  state,
  level,
}: {
  state: VoiceState
  level: number
}) {
  if (state === "off") {
    return (
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <MicOff className="size-4" />
        voice off
      </span>
    )
  }

  if (state === "transcribing") {
    return (
      <span className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        transcribing…
      </span>
    )
  }

  const listening = state === "listening"
  return (
    <span
      className={`flex items-center gap-2 text-sm ${
        listening ? "font-medium text-primary" : "text-muted-foreground"
      }`}
    >
      <Mic className={`size-4 ${listening ? "animate-pulse" : ""}`} />
      {listening ? "listening" : 'say "hey chris"'}
      {listening && (
        <span className="ml-1 flex h-3 items-end gap-0.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <span
              key={i}
              className="w-0.5 rounded-full bg-primary transition-all duration-75"
              style={{
                height: `${Math.max(
                  2,
                  Math.min(12, level * 14 * (i === 2 ? 1.2 : i % 2 ? 0.75 : 1)),
                )}px`,
              }}
            />
          ))}
        </span>
      )}
    </span>
  )
}
