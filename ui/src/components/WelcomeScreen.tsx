import { useEffect, useRef, useState } from "react"
import { speak } from "@/lib/bridge"

/**
 * The opening: Chris rolls in and greets whoever just signed in.
 *
 * The video is fixed and the name is not, so the name is DOM text over the
 * top rather than part of the recording — that is the whole reason this is
 * not a rendered video per operator.
 *
 * "Welcome" and "Welcome back" are different sentences on purpose. Being
 * recognised is the entire point of a returning greeting, and a machine that
 * greets a ten-year veteran as a stranger every morning is worse than one
 * that says nothing.
 */
const FALLBACK_MS = 6500

export function WelcomeScreen({
  name,
  returning,
  speaks,
  onDone,
}: {
  name: string
  returning: boolean
  /** Only one window may speak, or the greeting arrives twice over. */
  speaks: boolean
  onDone: () => void
}) {
  const [shown, setShown] = useState(false)
  const video = useRef<HTMLVideoElement | null>(null)
  const done = useRef(false)

  const greeting = returning ? "Welcome back" : "Welcome"
  const first = (name || "").trim().split(/\s+/)[0] || "there"

  // Held in a ref rather than listed as a dependency. `onDone` is redefined on
  // every render of App, and App re-renders several times a second while the
  // microphone reports its level — so an effect that depended on it ran again
  // on every frame of audio: the greeting was spoken forty times over, and the
  // failsafe timer was cancelled and restarted so often it could never fire.
  const latest = useRef(onDone)
  latest.current = onDone

  useEffect(() => {
    // Guarded because several things can end the welcome — the video ending,
    // the failsafe timer, a click — and the operator must not be walked
    // through the next screen twice.
    function finish() {
      if (done.current) return
      done.current = true
      latest.current()
    }

    const appear = window.setTimeout(() => setShown(true), 350)

    // A video that never fires `ended` — a missing file, a codec the webview
    // will not take, an autoplay block — must not strand somebody on a black
    // screen. This is the floor under all of those.
    const failsafe = window.setTimeout(finish, FALLBACK_MS)

    const el = video.current
    el?.addEventListener("ended", finish)

    // Play with the recording's own audio. There is no user gesture behind
    // this, and a webview may refuse to autoplay anything audible — so if it
    // is refused, unmute is dropped and it is played again silently. A silent
    // title sequence is a smaller loss than no title sequence.
    if (el) {
      el.muted = false
      void el.play?.().catch(() => {
        el.muted = true
        void el.play?.().catch(() => undefined)
      })
    }

    if (speaks) {
      // Spoken over the recording rather than after it. The video is fixed
      // and the name is not, which is the whole reason the greeting is not
      // simply part of the audio track.
      void speak([`${greeting}, ${first}.`])
    }

    return () => {
      window.clearTimeout(appear)
      window.clearTimeout(failsafe)
      el?.removeEventListener("ended", finish)
    }
    // Once per mount, deliberately. Nobody's name or greeting changes while
    // they are being greeted, and re-running this is what spoke over itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div
      className="relative h-full w-full overflow-hidden bg-black"
      onClick={onDone}
    >
      <video
        ref={video}
        className="absolute inset-0 h-full w-full object-cover"
        src="welcome-intro.mp4"
        autoPlay
        playsInline
        // No controls and no loop: this is a title sequence, not a video the
        // operator is meant to scrub through.
      />

      {/* The name sits over the video, so one recording greets everybody. */}
      <div
        className={`absolute inset-0 flex flex-col items-center justify-end gap-3 pb-[12vh] text-center transition-opacity duration-700 ${
          shown ? "opacity-100" : "opacity-0"
        }`}
      >
        <div className="bg-gradient-to-t from-black/80 to-transparent px-16 pb-10 pt-24">
          <p className="text-[2.2vw] uppercase tracking-[0.35em] text-white/70">
            {greeting}
          </p>
          <h1 className="mt-2 text-[5.5vw] font-bold leading-none text-white drop-shadow-[0_2px_24px_rgba(0,0,0,0.9)]">
            {name}
          </h1>
        </div>
      </div>

      <span className="absolute bottom-5 right-8 text-[11px] uppercase tracking-[0.25em] text-white/35">
        click to skip
      </span>
    </div>
  )
}
