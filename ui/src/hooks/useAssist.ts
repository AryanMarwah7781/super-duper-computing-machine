import { useCallback, useEffect, useRef, useState } from "react"
import {
  ask as bridgeAsk,
  cancel as bridgeCancel,
  installEventBus,
  onEvent,
  type ConnectionState,
  type TurnDto,
} from "@/lib/bridge"

/**
 * One entry in the conversation. Questions are kept alongside answers: an
 * answer with its question scrolled away is hard to trust, and an operator
 * comparing two procedures needs both on screen.
 */
export type ChatMessage =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; turn: TurnDto | null; error: string | null }

/** Omit<> does not distribute over a union, so the id-less shape is spelled out. */
type NewMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; turn: TurnDto | null; error: string | null }

export function useAssist() {
  const [state, setState] = useState<ConnectionState>("connecting")
  const [detail, setDetail] = useState("starting up")
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [busy, setBusy] = useState(false)
  const nextId = useRef(1)

  const push = useCallback((m: NewMessage) => {
    setMessages((prev) => [...prev, { ...m, id: nextId.current++ }])
  }, [])

  useEffect(() => {
    installEventBus()
    const offConnection = onEvent("connection", (d) => {
      const next = d as { state: ConnectionState; detail: string }
      setState(next.state)
      setDetail(next.detail)
    })
    return () => {
      offConnection()
    }
  }, [])

  const ask = useCallback(
    async (query: string, userId = "") => {
      setBusy(true)
      push({ role: "user", text: query })
      await bridgeCancel()
      const result = await bridgeAsk(query, "typed", userId)
      if (result.stale) {
        setBusy(false)
        return
      }
      push({
        role: "assistant",
        turn: result.ok ? result.turn : null,
        error: result.ok ? null : result.error,
      })
      setBusy(false)
    },
    [push],
  )

  /** Re-open a past question from the sidebar: both halves, from storage, with
   * no call to the devkit. */
  const appendHistory = useCallback(
    (query: string, turn: TurnDto | null) => {
      push({ role: "user", text: query })
      push({ role: "assistant", turn, error: null })
    },
    [push],
  )

  const clearConversation = useCallback(() => setMessages([]), [])

  return {
    state,
    detail,
    messages,
    busy,
    ask,
    appendHistory,
    clearConversation,
    cancel: bridgeCancel,
  }
}
