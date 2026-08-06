import { lazy, Suspense } from "react"
import { Mic } from "lucide-react"
import type { VoiceState } from "@/hooks/useAssist"

// Both are WebGL/canvas effects; keep them out of the main chunk so the window
// paints before they arrive.
const Strands = lazy(() => import("./Strands"))
const BorderGlow = lazy(() => import("./BorderGlow"))

// Brand blue and a lighter tint of it — the strands should read as this
// product, not as a generic demo.
const BRAND_STRANDS = ["#004884", "#2E7CC4", "#4A93D9", "#8FC1EA"]

/**
 * What the microphone is doing, at full size, in the conversation.
 *
 * The strands move continuously while listening, and the level meter is driven
 * by real audio — together they answer the question an operator actually has
 * mid-sentence: "is this thing hearing me?" A static graphic cannot.
 */
export function ListeningStage({ level }: { level: number }) {
  return (
    <div className="relative mx-auto my-6 h-44 max-w-3xl overflow-hidden rounded-2xl border bg-card">
      <Suspense fallback={<div className="h-full w-full bg-muted/30" />}>
        <Strands
          colors={BRAND_STRANDS}
          count={4}
          // Louder speech makes the strands livelier, so the animation is
          // reporting the microphone rather than merely decorating it.
          speed={0.4 + level * 1.6}
          amplitude={0.7 + level * 1.4}
          intensity={0.5 + level * 0.5}
          thickness={0.6}
          className="absolute inset-0"
        />
      </Suspense>

      <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
        <span className="flex items-center gap-2 text-lg font-medium text-foreground">
          <Mic className="size-5 animate-pulse text-primary" />
          Listening…
        </span>
        <span className="mt-1 text-sm text-muted-foreground">
          Ask your question, then pause.
        </span>
      </div>
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
  if (busy) return <ThinkingStage />
  return null
}
