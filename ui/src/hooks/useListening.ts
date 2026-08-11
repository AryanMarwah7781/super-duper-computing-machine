import { useCallback, useEffect, useRef, useState } from "react"
import { cancelListening, onEvent } from "@/lib/bridge"

/**
 * The countdown while Chris waits for an answer.
 *
 * Python owns the real deadline — it is the one holding the microphone — and
 * this only draws it. Two clocks would drift apart, and the visible one
 * reaching zero while the microphone was still open would be worse than no
 * countdown at all.
 *
 * So the bar is started by a `prompt` event from Python and stopped by the
 * matching reply. If the reply never comes the bar still empties, then stops:
 * an animation that runs forever reads as a hung app.
 */
export function useListening(replyEvent: string) {
  const [seconds, setSeconds] = useState(0)
  const [remaining, setRemaining] = useState(0)
  const timer = useRef<number | null>(null)

  const stop = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current)
      timer.current = null
    }
    setSeconds(0)
    setRemaining(0)
  }, [])

  useEffect(() => {
    const offPrompt = onEvent("prompt", (data) => {
      const total = Number((data as { seconds?: number })?.seconds ?? 0)
      if (!total) return
      setSeconds(total)
      setRemaining(total)
      if (timer.current !== null) window.clearInterval(timer.current)
      const started = Date.now()
      timer.current = window.setInterval(() => {
        const left = total - (Date.now() - started) / 1000
        if (left <= 0) {
          // Empty the bar, but leave the outcome to Python's event. Deciding
          // here that nothing was heard would race the reply that is already
          // being transcribed.
          setRemaining(0)
          if (timer.current !== null) window.clearInterval(timer.current)
          timer.current = null
        } else {
          setRemaining(left)
        }
      }, 100)
    })

    const offReply = onEvent(replyEvent, stop)
    // A reply to a different question still ends this one's countdown: only
    // one window is ever open, so any reply means ours is over.
    const offAny = onEvent("prompt_reply", stop)

    return () => {
      offPrompt()
      offReply()
      offAny()
      if (timer.current !== null) window.clearInterval(timer.current)
    }
  }, [replyEvent, stop])

  /** They answered by tapping. Close the microphone rather than leaving it
   *  open behind a screen that has already moved on. */
  const dismiss = useCallback(() => {
    stop()
    void cancelListening()
  }, [stop])

  return {
    listening: seconds > 0 && remaining > 0,
    seconds,
    remaining,
    /** 1 at the start, 0 when the window closes. */
    fraction: seconds > 0 ? remaining / seconds : 0,
    dismiss,
    stop,
  }
}
