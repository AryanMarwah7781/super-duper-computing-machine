import { beforeEach, describe, expect, it, vi } from "vitest"
import { ask, installEventBus, onEvent } from "./bridge"

beforeEach(() => {
  installEventBus()
})

describe("event bus", () => {
  it("delivers an emitted event to a subscriber", () => {
    const seen: unknown[] = []
    onEvent("connection", (d) => seen.push(d))
    window.assist!.emit({ event: "connection", data: { state: "ready" } })
    expect(seen).toEqual([{ state: "ready" }])
  })

  it("stops delivering after unsubscribe", () => {
    const seen: unknown[] = []
    const off = onEvent("error", (d) => seen.push(d))
    off()
    window.assist!.emit({ event: "error", data: { message: "x" } })
    expect(seen).toEqual([])
  })

  it("ignores an event nobody subscribed to", () => {
    expect(() =>
      window.assist!.emit({ event: "nobody-listening", data: {} }),
    ).not.toThrow()
  })
})

describe("ask", () => {
  it("calls through the pywebview bridge", async () => {
    const spy = vi.fn().mockResolvedValue({ ok: true, turn: null, error: null })
    window.pywebview = { api: { ask: spy } }
    await ask("how do i fill the tank")
    expect(spy).toHaveBeenCalledWith("how do i fill the tank", "typed")
  })

  it("reports a clear error when the bridge is missing", async () => {
    window.pywebview = undefined
    const result = await ask("anything")
    expect(result.ok).toBe(false)
    expect(result.error).toMatch(/bridge/i)
  })
})
