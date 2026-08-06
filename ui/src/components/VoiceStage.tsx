import { lazy, Suspense } from "react"
import { Mic } from "lucide-react"
import type { VoiceState } from "@/hooks/useAssist"

// A canvas effect; keep it out of the main chunk so the window paints first.
const BorderGlow = lazy(() => import("./BorderGlow"))

/**
 * Bars driven by the real microphone level.
 *
 * Deliberately plain: the point is to answer "is this hearing me?" while the
 * operator is mid-sentence, and bars that move with their voice do that better
 * than an ambient effect. Silence must look like silence.
 */
export function ListeningStage({ level }: { level: number }) {
  const bars = [0.55, 0.8, 1, 0.85, 0.6, 0.9, 0.7]
  return (
    <div className="mx-auto my-6 flex max-w-3xl flex-col items-center gap-4
                    rounded-2xl border bg-card px-6 py-8">
      <span className="flex h-14 items-end gap-1.5">
        {bars.map((weight, i) => (
          <span
            key={i}
            className="w-2 rounded-full bg-primary transition-[height] duration-75"
            style={{ height: `${Math.max(6, Math.min(56, level * 150 * weight))}px` }}
          />
        ))}
      </span>
      <span className="flex items-center gap-2 text-lg font-medium">
        <Mic className="size-5 animate-pulse text-primary" />
        Listening…
      </span>
      <span className="-mt-2 text-sm text-muted-foreground">
        Ask your question, then pause.
      </span>
    </div>
  )
}

/**
 * The gap between a question landing and an answer appearing.
 *
 * That gap is real — retrieval takes about ten seconds on the board — so it
 * needs to look like work in progress rather than a hang.
 */
export function ThinkingStage({ label = "Searching the manual…" }: { label?: string }) {
  return (
    <div className="mx-auto my-6 max-w-3xl">
      <Suspense
        fallback={
          <div className="h-20 animate-pulse rounded-2xl border bg-muted/30" />
        }
      >
        <BorderGlow
          borderRadius={16}
          glowIntensity={1.1}
          glowRadius={120}
          animated
          colors={["#004884", "#4A93D9", "#8FC1EA"]}
          className="w-full"
        >
          <div className="flex items-center gap-3 px-6 py-5">
            <span className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="size-1.5 animate-bounce rounded-full bg-primary"
                  style={{ animationDelay: `${i * 140}ms` }}
                />
              ))}
            </span>
            <span className="text-base text-muted-foreground">{label}</span>
          </div>
        </BorderGlow>
      </Suspense>
    </div>
  )
}

export function VoiceStage({
  state,
  level,
  busy,
}: {
  state: VoiceState
  level: number
  busy: boolean
}) {
  if (state === "listening") return <ListeningStage level={level} />
  if (state === "transcribing") return <ThinkingStage label="Making out what you said…" />
  if (state === "asking" || busy) return <ThinkingStage />
  return null
}
