import { describe, expect, it } from "vitest"
import { isVoiceOwner, readRole, showsChat, showsLesson } from "./role"

describe("readRole", () => {
  it("reads the role Python launched this window with", () => {
    expect(readRole("?role=chat")).toBe("chat")
    expect(readRole("?role=lesson")).toBe("lesson")
    expect(readRole("?role=all")).toBe("all")
  })

  it("shows everything when no role was given", () => {
    // A plain browser, or `npm run dev`. Neither should be a black screen.
    expect(readRole("")).toBe("all")
    expect(readRole("?")).toBe("all")
  })

  it("falls back to everything on a typo rather than showing nothing", () => {
    expect(readRole("?role=chatt")).toBe("all")
    expect(readRole("?role=")).toBe("all")
    expect(readRole("?role=LESSON")).toBe("all")
  })

  it("ignores other query parameters", () => {
    expect(readRole("?dev=1&role=lesson&x=2")).toBe("lesson")
  })
})

describe("what each panel draws", () => {
  it("the chat panel draws the chatbot and not the lesson plan", () => {
    expect(showsChat("chat")).toBe(true)
    expect(showsLesson("chat")).toBe(false)
  })

  it("the lesson panel draws the lesson plan and not the chatbot", () => {
    expect(showsLesson("lesson")).toBe(true)
    expect(showsChat("lesson")).toBe(false)
  })

  it("one window draws both", () => {
    expect(showsChat("all")).toBe(true)
    expect(showsLesson("all")).toBe(true)
  })
})

describe("who speaks", () => {
  it("only one panel, or the greeting arrives twice over", () => {
    expect(isVoiceOwner("chat")).toBe(true)
    expect(isVoiceOwner("lesson")).toBe(false)
    expect(isVoiceOwner("all")).toBe(true)
  })

  it("exactly one owner in the two-panel arrangement", () => {
    const owners = (["chat", "lesson"] as const).filter(isVoiceOwner)
    expect(owners).toHaveLength(1)
  })
})
