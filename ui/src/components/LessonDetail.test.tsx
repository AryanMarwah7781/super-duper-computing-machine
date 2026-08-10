import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import type { OpenLesson } from "@/hooks/useLessons"
import { LessonDetail } from "./LessonDetail"

const LESSON: OpenLesson = {
  category: "CommandARM Lessons",
  sync: true,
  detail: "Watching the CommandARM. Steps complete as you operate the console.",
  lesson: {
    id: "groups",
    name: "One at a Time — Rate, Reset & Idle",
    summary: "",
    steps: [
      {
        header: "Select Rate 1",
        body: "Press Rate 1 on the console.",
        icon: { label: "RATE 1", glyph: "1" },
        sync: {
          signals: ["PLT_AIC_Rate1Control"],
          condition: "equals",
          value: "1",
          requires_step: null,
        },
      },
      {
        header: "Move to Rate 2",
        body: "Rate 1 goes out on its own.",
        sync: {
          signals: ["PLT_AIC_Rate2Control"],
          condition: "equals",
          value: "1",
          requires_step: 1,
        },
      },
    ],
  },
}

const BASE = {
  open: LESSON,
  onBack: () => {},
  onTick: () => {},
  onRestart: () => {},
}

describe("LessonDetail", () => {
  it("shows the procedure and where the operator has got to", () => {
    render(<LessonDetail {...BASE} done={[1]} />)
    expect(screen.getByText("Select Rate 1")).toBeDefined()
    expect(screen.getByText("1 of 2 complete")).toBeDefined()
  })

  it("marks only the step the machine reported", () => {
    render(<LessonDetail {...BASE} done={[1]} />)
    const steps = screen.getAllByRole("listitem")
    expect(steps[0].dataset.complete).toBe("true")
    expect(steps[1].dataset.complete).toBe("false")
  })

  it("says which step the console is being watched for", () => {
    render(<LessonDetail {...BASE} done={[1]} />)
    // The badge belongs on step 2 — the next one — not on the whole lesson.
    expect(screen.getAllByText(/watching the console/i)).toHaveLength(1)
  })

  it("does not claim to be watching a lesson played in the simulator", () => {
    const offline: OpenLesson = { ...LESSON, sync: false, detail: "" }
    render(<LessonDetail {...BASE} open={offline} done={[]} />)
    expect(screen.queryByText(/watching the console/i)).toBeNull()
  })

  it("lets a step be ticked off by hand when the log missed it", () => {
    const ticked: number[] = []
    render(<LessonDetail {...BASE} done={[]} onTick={(i) => ticked.push(i)} />)
    fireEvent.click(screen.getAllByRole("button", { name: /mark done/i })[1])
    expect(ticked).toEqual([2])
  })

  it("offers no way to un-tick a step that is already done", () => {
    render(<LessonDetail {...BASE} done={[1, 2]} />)
    expect(screen.queryByRole("button", { name: /mark done/i })).toBeNull()
  })

  it("names the signal behind a step that has not completed", () => {
    // The one question this screen must answer: why has it not ticked over?
    render(<LessonDetail {...BASE} done={[]} />)
    expect(screen.getByText("PLT_AIC_Rate1Control")).toBeDefined()
  })

  it("can start the lesson over", () => {
    const onRestart = vi.fn()
    render(<LessonDetail {...BASE} done={[1, 2]} onRestart={onRestart} />)
    fireEvent.click(screen.getByRole("button", { name: /start over/i }))
    expect(onRestart).toHaveBeenCalled()
  })

  it("says so when every step is done", () => {
    render(<LessonDetail {...BASE} done={[1, 2]} />)
    expect(screen.getByText(/lesson complete/i)).toBeDefined()
  })
})
