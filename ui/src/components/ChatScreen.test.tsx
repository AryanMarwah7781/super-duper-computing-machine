import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { TurnDto } from "@/lib/bridge"
import { ChatScreen } from "./ChatScreen"

const BASE = {
  entries: [],
  busy: false,
  unavailable: false,
  detail: "connected",
  error: null,
  state: "ready" as const,
  onAsk: () => {},
  onReopen: () => {},
}

const TURN: TurnDto = {
  plan: { kind: "cached", chunk_ids: [1], reason: "top=procedure" },
  answer: {
    display_text: "Step 1: Park the machine.\n\n_Manual page 12._",
    spoken_segments: [],
    safety: [],
    citations: [],
    images: [],
    render_version: "v4.0",
    source_hash: "x",
  },
  candidates: [],
  timing: { total_ms: 1200 },
}

describe("ChatScreen", () => {
  it("greets with the farming prompt before anything is asked", () => {
    render(<ChatScreen {...BASE} turn={null} />)
    expect(screen.getByText(/let's start farming/i)).toBeDefined()
  })

  it("shows the collaboration credit on the empty state", () => {
    render(<ChatScreen {...BASE} turn={null} />)
    expect(screen.getByText("L&T")).toBeDefined()
    expect(screen.getByText("CNH")).toBeDefined()
    expect(screen.getByText(/collaboration/i)).toBeDefined()
  })

  it("keeps the question box available while empty", () => {
    render(<ChatScreen {...BASE} turn={null} />)
    expect(screen.getByPlaceholderText(/ask about the r4045/i)).toBeDefined()
  })

  it("replaces the greeting with the answer once one arrives", () => {
    render(<ChatScreen {...BASE} turn={TURN} />)
    expect(screen.queryByText(/let's start farming/i)).toBeNull()
    expect(screen.getByText(/Park the machine/)).toBeDefined()
  })

  it("disables the question box when the devkit is unavailable", () => {
    render(
      <ChatScreen {...BASE} turn={null} unavailable detail="devkit unreachable" />,
    )
    const input = screen.getByPlaceholderText(
      /ask about the r4045/i,
    ) as HTMLInputElement
    expect(input.disabled).toBe(true)
    expect(screen.getByText(/devkit unreachable/i)).toBeDefined()
  })
})
