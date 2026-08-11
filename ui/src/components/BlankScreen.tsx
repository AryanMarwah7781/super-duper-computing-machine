import { useRef } from "react"

/**
 * The panel before anybody has signed in. Black, and that is the whole point.
 *
 * Sign-in happens at the kiosk on the board, not here. Until a name arrives
 * these screens are meant to look switched off — a login form on a panel
 * nobody is supposed to touch is an invitation to touch it, and two ways in
 * that can disagree about who is at the machine.
 *
 * Which leaves the morning the board is unplugged. Three taps anywhere brings
 * this app's own sign-in screen up, and with it the Admin button — the only
 * route to the trainer's screen once the kiosk owns the front door. Three
 * rather than one, because the operator's first instinct in front of a black
 * screen is to touch it, and one tap would put the fallback in front of them
 * every time.
 */
const TAPS = 3
const WITHIN_MS = 2000

export function BlankScreen({ onReveal }: { onReveal: () => void }) {
  const taps = useRef<number[]>([])

  function tap() {
    const now = Date.now()
    taps.current = [...taps.current, now].filter((t) => now - t < WITHIN_MS)
    if (taps.current.length >= TAPS) {
      taps.current = []
      onReveal()
    }
  }

  return (
    <div
      className="h-screen w-screen bg-black"
      onClick={tap}
      // Nothing to read, nothing to announce. The screen is off as far as
      // anybody standing in front of it is concerned.
      aria-hidden="true"
    />
  )
}
