/**
 * The UI's entire connection to the outside world.
 *
 * There is no fetch in this application. Python owns the network, so every call
 * goes through window.pywebview.api, and Python pushes state changes back
 * through window.assist.emit.
 */

export type ConnectionState = "connecting" | "ready" | "warming" | "offline"

export type ImageDto = {
  id_code: string
  image_path: string
  caption: string
  step_num: number | null
}

export type TurnDto = {
  plan: { kind: string; chunk_ids: number[]; reason: string }
  answer: {
    display_text: string
    spoken_segments: string[]
    safety: { level: string; text: string; page: number | null }[]
    citations: { page: number; procedure_name: string; method: string }[]
    images: ImageDto[]
    render_version: string
    source_hash: string
  } | null
  candidates: {
    chunk_id: number
    score: number
    content_type: string
    procedure_name: string
    page: number | null
  }[]
  timing: Record<string, number>
}

export type AskResult = {
  ok: boolean
  turn: TurnDto | null
  error: string | null
  stale?: boolean
}

type Handler = (data: unknown) => void

declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...a: unknown[]) => Promise<unknown>>
    }
    assist?: { emit: (envelope: { event: string; data: unknown }) => void }
  }
}

const handlers = new Map<string, Set<Handler>>()

export function installEventBus(): void {
  handlers.clear()
  window.assist = {
    emit: ({ event, data }) => {
      handlers.get(event)?.forEach((h) => h(data))
    },
  }
}

export function onEvent(name: string, handler: Handler): () => void {
  if (!handlers.has(name)) handlers.set(name, new Set())
  handlers.get(name)!.add(handler)
  return () => {
    handlers.get(name)?.delete(handler)
  }
}

function bridge() {
  return window.pywebview?.api
}

export async function ask(query: string, source = "typed"): Promise<AskResult> {
  const api = bridge()
  if (!api) {
    return { ok: false, turn: null, error: "the Python bridge is not available" }
  }
  return (await api.ask(query, source)) as AskResult
}

export async function cancel(): Promise<void> {
  await bridge()?.cancel()
}
