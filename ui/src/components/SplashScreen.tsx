import { useEffect, useState } from "react"
import SplitFlapText from "./SplitFlapText"
import { LttsLogo } from "./Brand"
import { whenBridgeReady } from "@/lib/bridge"

/**
 * Boot screen, shown while the app actually has work to do.
 *
 * The stages are real, not a timed fiction: the bridge genuinely arrives after
 * mount, and the lanyard chunk is 3.3 MB of three/rapier plus a 2.4 MB model
 * that otherwise pops in halfway through the login screen. Waiting here turns
 * a visible stutter into a deliberate opening.
 *
 * MIN_DWELL keeps each caption on screen long enough to read — without it a
 * warm start flashes through every stage in a few frames, which reads as a
 * glitch rather than a boot.
 */
const MIN_DWELL = 900

const STAGES = [
  "WELCOME TO LTTS FARMING ASSIST",
  "CONNECTING TO DEVKIT",
  "LOADING MODELS",
  "READY",
] as const

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms))
}

export function SplashScreen({ onDone }: { onDone: () => void }) {
  const [stage, setStage] = useState(0)

  useEffect(() => {
    let cancelled = false

    async function boot() {
      // 1. Greet.
      await sleep(MIN_DWELL)
      if (cancelled) return

      // 2. Wait for the Python bridge to be injected.
      setStage(1)
      await Promise.all([whenBridgeReady(), sleep(MIN_DWELL)])
      if (cancelled) return

      // 3. Pull the heavy 3D chunk in now, so the badge rack is ready when the
      //    login screen mounts. Failure is not fatal — Suspense still covers it.
      setStage(2)
      await Promise.all([
        import("./Lanyard").catch(() => undefined),
        sleep(MIN_DWELL),
      ])
      if (cancelled) return

      setStage(3)
      await sleep(700)
      if (!cancelled) onDone()
    }

    void boot()
    return () => {
      cancelled = true
    }
  }, [onDone])

  return (
    <div className="flex h-full flex-col items-center justify-center gap-10 bg-background px-6">
      <LttsLogo className="h-20 w-auto" />

      <SplitFlapText
        text={STAGES[stage]}
        charset="alpha"
        loop={false}
        flipDuration={0.32}
        stagger={0.028}
        flipsPerChar={2}
        tileColor="#004884"
        textColor="#ffffff"
        tileRadius="4px"
        gap="3px"
        fontSize="clamp(14px, 2.1vw, 26px)"
        aria-live="polite"
      />

      <div className="flex items-center gap-2">
        {STAGES.map((_, i) => (
          <span
            key={i}
            className={`h-1.5 rounded-full transition-all duration-500 ${
              i <= stage ? "w-8 bg-primary" : "w-4 bg-muted"
            }`}
          />
        ))}
      </div>

      <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
        L&amp;T Technology Services &nbsp;×&nbsp; CNH
      </span>
    </div>
  )
}
