import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import type { TurnDto } from "@/lib/bridge"
import { AnswerView } from "./AnswerView"

const PROCEDURE: TurnDto = {
  plan: { kind: "cached", chunk_ids: [412], reason: "top=procedure score=8.14" },
  answer: {
    display_text:
      "**WARNING:** Keep bystanders clear.\nStep 1: Park the machine.\n" +
      "[PHOTO: Fill cap location]\nStep 2: Open the fill cap.\n\n_Manual page 472._",
    spoken_segments: [],
    safety: [{ level: "WARNING", text: "Keep bystanders clear.", page: 472 }],
    citations: [
      { page: 472, procedure_name: "Fill Solution Tank", method: "image" },
    ],
    images: [
      {
        id_code: "N1",
        image_path: "images/fill_cap.png",
        caption: "Fill cap location",
        step_num: 1,
      },
    ],
    render_version: "v4.0",
    source_hash: "abc",
  },
  candidates: [],
  timing: { total_ms: 4520 },
}

const OOS: TurnDto = {
  plan: { kind: "oos", chunk_ids: [], reason: "best of 5 candidates -3.63 < 0.0" },
  answer: null,
  candidates: [],
  timing: { total_ms: 4305 },
}

describe("AnswerView", () => {
  it("renders steps and the citation", () => {
    render(<AnswerView turn={PROCEDURE} />)
    expect(screen.getByText(/Park the machine/)).toBeDefined()
    expect(screen.getByText(/Open the fill cap/)).toBeDefined()
    expect(screen.getByText(/page 472/i)).toBeDefined()
  })

  it("renders safety above the first step", () => {
    const { container } = render(<AnswerView turn={PROCEDURE} />)
    const html = container.innerHTML
    expect(html.indexOf("Keep bystanders clear")).toBeLessThan(
      html.indexOf("Park the machine"),
    )
  })

  it("renders the photo against the local bundle server", () => {
    render(<AnswerView turn={PROCEDURE} />)
    const img = screen.getByAltText("Fill cap location")
    expect(img.getAttribute("src")).toBe("/images/fill_cap.png")
  })

  it("says it does not know rather than guessing, on oos", () => {
    render(<AnswerView turn={OOS} />)
    expect(screen.getByText(/don't know/i)).toBeDefined()
  })

  it("marks a synthesize answer as an unsynthesised excerpt", () => {
    render(
      <AnswerView
        turn={{ ...PROCEDURE, plan: { ...PROCEDURE.plan, kind: "synthesize" } }}
      />,
    )
    expect(screen.getByText(/excerpt/i)).toBeDefined()
  })

  it("renders nothing when there is no turn", () => {
    const { container } = render(<AnswerView turn={null} />)
    expect(container.textContent?.trim()).toBe("")
  })
})

describe("commands", () => {
  const command = (text: string, reason: string): TurnDto => ({
    plan: { kind: "command", chunk_ids: [], reason },
    answer: {
      display_text: text,
      spoken_segments: [text],
      safety: [],
      citations: [],
      images: [],
      render_version: "command",
      source_hash: "",
    },
    candidates: [],
    timing: { total_ms: 0 },
  })

  it("shows a completed command as an action, not an answer", () => {
    render(<AnswerView turn={command("Folding the boom.", "fold_boom ok")} />)
    expect(screen.getByText("Folding the boom.")).toBeDefined()
  })

  it("distinguishes a failed command from a successful one", () => {
    const { container: good } = render(
      <AnswerView turn={command("Folding the boom.", "fold_boom ok")} />,
    )
    const { container: bad } = render(
      <AnswerView
        turn={command("I could not reach the machine.", "fold_boom FAILED")}
      />,
    )
    expect(good.innerHTML).not.toEqual(bad.innerHTML)
    expect(bad.innerHTML).toContain("destructive")
  })
})

describe("chat", () => {
  const chat = (text: string): TurnDto => ({
    plan: { kind: "chat", chunk_ids: [], reason: "smalltalk" },
    answer: {
      display_text: text,
      spoken_segments: [text],
      safety: [],
      citations: [],
      images: [],
      render_version: "chat",
      source_hash: "",
    },
    candidates: [],
    timing: { total_ms: 0 },
  })

  it("shows what Chris said", () => {
    render(<AnswerView turn={chat("I'm here. What do you need?")} />)
    expect(screen.getByText("I'm here. What do you need?")).toBeDefined()
  })

  it("never puts a manual page under something Chris said", () => {
    const { container } = render(chat("I'm fine.") && <AnswerView turn={chat("I'm fine.")} />)
    expect(container.textContent).not.toContain("Manual page")
  })
})

describe("a recalled answer", () => {
  it("says the answer came off this machine", () => {
    // Instant because it was asked before, not because the board got fast.
    render(<AnswerView turn={{ ...PROCEDURE, recalled: true }} />)
    expect(screen.getByText(/answered before/i)).toBeDefined()
  })

  it("says nothing when the board answered it just now", () => {
    render(<AnswerView turn={PROCEDURE} />)
    expect(screen.queryByText(/answered before/i)).toBeNull()
  })

  it("still renders the answer itself", () => {
    render(<AnswerView turn={{ ...PROCEDURE, recalled: true }} />)
    expect(screen.getByText(/Park the machine/)).toBeDefined()
    expect(screen.getByText(/Keep bystanders clear/)).toBeDefined()
  })
})
