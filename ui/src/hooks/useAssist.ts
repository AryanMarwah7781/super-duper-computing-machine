import { useCallback, useEffect, useState } from "react"
import {
  ask as bridgeAsk,
  cancel as bridgeCancel,
  installEventBus,
  onEvent,
  type ConnectionState,
  type TurnDto,
} from "@/lib/bridge"

export function useAssist() {
  const [state, setState] = useState<ConnectionState>("connecting")
  const [detail, setDetail] = useState("starting up")
  const [turn, setTurn] = useState<TurnDto | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    installEventBus()
    const offConnection = onEvent("connection", (d) => {
      const next = d as { state: ConnectionState; detail: string }
      setState(next.state)
      setDetail(next.detail)
      // A stale procedure shown as current is the worst failure this app has.
      if (next.state === "offline") setTurn(null)
    })
    const offError = onEvent("error", (d) => {
      setError((d as { message: string }).message)
    })
    return () => {
      offConnection()
      offError()
    }
  }, [])

  const ask = useCallback(async (query: string) => {
    setBusy(true)
    setError(null)
    await bridgeCancel()
    const result = await bridgeAsk(query)
    if (result.stale) {
      setBusy(false)
      return
    }
    if (result.ok) {
      setTurn(result.turn)
    } else {
      setTurn(null)
      setError(result.error)
    }
    setBusy(false)
  }, [])

  return { state, detail, turn, error, busy, ask, cancel: bridgeCancel }
}
