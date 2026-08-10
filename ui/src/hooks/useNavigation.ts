import { useCallback, useState } from "react"

export type ScreenName =
  | "login"
  | "home"
  | "chat"
  | "lesson"
  | "simulator"
  | "admin"

/**
 * A browser-style history stack.
 *
 * Going somewhere new from the middle of the stack truncates whatever was
 * ahead, which is what a back/forward pair has to do — otherwise "forward"
 * would walk into a branch the operator abandoned.
 */
export function useNavigation(initial: ScreenName = "login") {
  const [stack, setStack] = useState<ScreenName[]>([initial])
  const [index, setIndex] = useState(0)

  const go = useCallback(
    (screen: ScreenName) => {
      setStack((prev) => [...prev.slice(0, index + 1), screen])
      setIndex((i) => i + 1)
    },
    [index],
  )

  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])

  const forward = useCallback(
    () => setIndex((i) => Math.min(stack.length - 1, i + 1)),
    [stack.length],
  )

  /** Sign out: forget the whole trail so the next person cannot walk back
   * into the previous operator's session. */
  const reset = useCallback((screen: ScreenName = "login") => {
    setStack([screen])
    setIndex(0)
  }, [])

  return {
    screen: stack[index],
    canGoBack: index > 0,
    canGoForward: index < stack.length - 1,
    go,
    back,
    forward,
    reset,
  }
}
