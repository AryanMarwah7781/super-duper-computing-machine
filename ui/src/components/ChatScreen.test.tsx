import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { ChatMessage } from "@/hooks/useAssist"
import type { TurnDto } from "@/lib/bridge"
import { ChatScreen } from "./ChatScreen"

const BASE = {
  entries: [],
  busy: false,
  unavailable: false,
  detail: "connected",
  state: "ready" as const,
  onAsk: () => {},
  onReopen: () => {},
}

function turn(text: string): TurnDto {
  return {
    plan: { kind: "cached", chunk_ids: [1], reason: "top=procedure" },
    answer: {
      display_text: `Step 1: ${text}\n\n_Manual page 12._`,
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
}

const CONVERSATION: ChatMessage[] = [
  { id: 1, role: "user", text: "how do i fill the tank" },
  { id: 2, role: "assistant", turn: turn("Park the machine."), error: null },
  { id: 3, role: "user", text: "how do i fold the boom" },
  { id: 4, role: "assistant", turn: turn("Lower the boom."), error: null },
]

describe("ChatScreen", () => {
  it("greets with the farming prompt before anything is asked", () => {
    render(<ChatScreen {...BASE} messages={[]} />)
    expect(screen.getByText(/let's start farming/i)).toBeDefined()
  })

  it("shows the collaboration credit on the empty state", () => {
    render(<ChatScreen {...BASE} messages={[]} />)
    // The L&T half is the supplied logo artwork, not type.
    expect(screen.getByText("L&T")).toBeDefined()
    expect(screen.getByText("CNH")).toBeDefined()
    expect(screen.getByText(/collaboration/i)).toBeDefined()
  })

  it("keeps the question on screen next to its answer", () => {
    render(<ChatScreen {...BASE} messages={CONVERSATION.slice(0, 2)} />)
    expect(screen.getByText("how do i fill the tank")).toBeDefined()
    expect(screen.getByText(/Park the machine/)).toBeDefined()
  })

  it("preserves earlier turns when a new one arrives", () => {
    render(<ChatScreen {...BASE} messages={CONVERSATION} />)
    expect(screen.getByText("how do i fill the tank")).toBeDefined()
    expect(screen.getByText(/Park the machine/)).toBeDefined()
    expect(screen.getByText("how do i fold the boom")).toBeDefined()
    expect(screen.getByText(/Lower the boom/)).toBeDefined()
  })

  it("renders the question above its own answer", () => {
    const { container } = render(<ChatScreen {...BASE} messages={CONVERSATION} />)
    const html = container.innerHTML
    expect(html.indexOf("how do i fill the tank")).toBeLessThan(
      html.indexOf("Park the machine"),
    )
  })

  it("shows a failed turn as an error without losing the question", () => {
    render(
      <ChatScreen
        {...BASE}
        messages={[
          { id: 1, role: "user", text: "anything" },
          { id: 2, role: "assistant", turn: null, error: "cannot reach the devkit" },
        ]}
      />,
    )
    expect(screen.getByText("anything")).toBeDefined()
    expect(screen.getByText(/cannot reach the devkit/)).toBeDefined()
  })

  it("keeps the question box available while empty", () => {
    render(<ChatScreen {...BASE} messages={[]} />)
    expect(screen.getByPlaceholderText(/ask about the r4045/i)).toBeDefined()
  })

  it("disables the question box when the devkit is unavailable", () => {
    render(
      <ChatScreen {...BASE} messages={[]} unavailable detail="devkit unreachable" />,
    )
    const input = screen.getByPlaceholderText(
      /ask about the r4045/i,
    ) as HTMLInputElement
    expect(input.disabled).toBe(true)
    expect(screen.getByText(/devkit unreachable/i)).toBeDefined()
  })
})
