import { useEffect, useRef } from "react"
import { useListening } from "@/hooks/useListening"
import { askChoiceAloud, onEvent, speak } from "@/lib/bridge"

/**
 * The fork, straight after the welcome: ask the sprayer something, or carry
 * on with the lesson plan.
 *
 * Both panels show this at once. Whichever monitor the operator is looking at
 * has the answer on it, and the two tiles are placed so that the chatbot tile
 * points at the chatbot's monitor and the lesson tile at the lesson plan's.
 *
 * "Continue" and "Start" are different words for a reason — somebody four
 * lessons in should not be invited to begin.
 */
export type Choice = "chat" | "lesson"

export function ChoiceScreen({
  name,
  returning,
  speaks,
  onPick,
}: {
  name: string
  returning: boolean
  speaks: boolean
  onPick: (choice: Choice) => void
}) {
  const asked = useRef(false)
  const first = (name || "").trim().split(/\s+/)[0] || "there"
  const lessonVerb = returning ? "Continue" : "Start"
  const listen = useListening("choice_heard")

  useEffect(() => {
    // Once per mount. Both panels mount this, but only the voice owner speaks,
    // and React in strict mode mounts twice in development.
    if (!speaks || asked.current) return
    asked.current = true

    let cancelled = false
    void (async () => {
      await speak([
        `So, ${first}.`,
        "Would you like to learn more about the sprayer,",
        `or ${lessonVerb.toLowerCase()} your lesson plan?`,
      ])
      // The microphone opens after the question, never during it. The wake
      // gate is shut while the app talks precisely because it would otherwise
      // record its own voice, and an answer window is no different.
      if (!cancelled) void askChoiceAloud()
    })()

    return () => {
      cancelled = true
    }
  }, [speaks, first, lessonVerb])

  // Python resolves the reply and navigates, so nothing to do on a hit. This
  // is only here to say so when it did not understand — silence after
  // answering out loud reads as a broken microphone.
  useEffect(() => {
    return onEvent("choice_heard", (data) => {
      const d = data as { choice: string | null }
      if (d?.choice === "cancel") listen.stop()
    })
  }, [listen])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "1") onPick("chat")
      if (e.key === "2") onPick("lesson")
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onPick])

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-12 bg-black px-[6vw]">
      <div className="text-center">
        <img
          src="chris.png"
          alt=""
          className="mx-auto h-[14vh] w-auto drop-shadow-[0_6px_30px_rgba(255,255,255,0.15)]"
        />
        <h1 className="mt-6 text-[2.6vw] font-semibold text-white">
          What would you like to do, {first}?
        </h1>
      </div>

      <div className="flex w-full max-w-[70vw] items-stretch justify-center gap-[3vw]">
        <Tile
          index={1}
          title="Learn about the sprayer"
          blurb="Ask anything from the operator's manual — procedures, settings, what a control does."
          onClick={() => {
            listen.dismiss()
            onPick("chat")
          }}
          icon={<ChatIcon />}
        />
        <Tile
          index={2}
          title={`${lessonVerb} your lesson plan`}
          blurb={
            returning
              ? "Pick up where you left off. Your progress is saved."
              : "Guided procedures on the machine, step by step."
          }
          onClick={() => {
            listen.dismiss()
            onPick("lesson")
          }}
          icon={<LessonIcon />}
        />
      </div>

      {listen.listening ? (
        <Listening remaining={listen.remaining} fraction={listen.fraction} />
      ) : (
        <p className="text-[11px] uppercase tracking-[0.25em] text-white/35">
          say it, tap it, or press 1 or 2
        </p>
      )}
    </div>
  )
}

/**
 * "I'm listening", with the time left.
 *
 * A visible deadline matters more than it looks: without it, somebody who
 * takes a moment to think has no idea whether the microphone is still open,
 * and starts their answer just as it closes.
 */
export function Listening({
  remaining,
  fraction,
}: {
  remaining: number
  fraction: number
}) {
  return (
    <div className="flex w-full max-w-[30vw] flex-col items-center gap-3">
      <div className="flex items-center gap-3">
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-70" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-primary" />
        </span>
        <span className="text-sm uppercase tracking-[0.25em] text-white/70">
          listening — {Math.ceil(remaining)}s
        </span>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-100 ease-linear"
          style={{ width: `${Math.max(0, Math.min(1, fraction)) * 100}%` }}
        />
      </div>
      <span className="text-[11px] uppercase tracking-[0.25em] text-white/30">
        or tap one
      </span>
    </div>
  )
}

function Tile({
  index,
  title,
  blurb,
  icon,
  onClick,
}: {
  index: number
  title: string
  blurb: string
  icon: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-1 flex-col items-center gap-5 rounded-3xl border border-white/12 bg-white/[0.04] px-[3vw] py-[5vh] text-center transition-all duration-200 hover:-translate-y-1 hover:border-white/35 hover:bg-white/[0.09] focus:outline-none focus-visible:border-white focus-visible:ring-2 focus-visible:ring-white/60"
    >
      <span className="flex h-[10vh] w-[10vh] items-center justify-center rounded-2xl bg-primary/15 text-primary transition-colors group-hover:bg-primary/25">
        {icon}
      </span>
      <span className="text-[1.6vw] font-semibold leading-tight text-white">
        {title}
      </span>
      <span className="max-w-[24ch] text-[0.95vw] leading-relaxed text-white/55">
        {blurb}
      </span>
      <span className="mt-auto pt-4 text-[11px] uppercase tracking-[0.3em] text-white/30">
        press {index}
      </span>
    </button>
  )
}

/* Inline rather than linked: the bundle is served over a local socket with a
   strict policy, and two icons are not worth a sprite sheet. */

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-[5vh] w-[5vh]"
         stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.4-.7L3 21l1.9-5.1A8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z" />
      <path d="M9.2 9.6a2.8 2.8 0 0 1 5.5.8c0 1.9-2.8 2.4-2.8 2.4" />
      <path d="M12 17h.01" />
    </svg>
  )
}

function LessonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-[5vh] w-[5vh]"
         stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
         strokeLinejoin="round" aria-hidden="true">
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H10a2.5 2.5 0 0 1 2 1 2.5 2.5 0 0 1 2-1h4.5A1.5 1.5 0 0 1 20 5.5v12a1.5 1.5 0 0 1-1.5 1.5H14a2.5 2.5 0 0 0-2 1 2.5 2.5 0 0 0-2-1H5.5A1.5 1.5 0 0 1 4 17.5Z" />
      <path d="M12 5v14" />
      <path d="m15.5 10.5 1.6 1.6 3-3" />
    </svg>
  )
}
