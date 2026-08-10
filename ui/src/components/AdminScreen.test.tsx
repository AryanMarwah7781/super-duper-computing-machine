import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { AdminScreen } from "./AdminScreen"

const LESSONS = [
  { id: "spray", name: "Spray Lesson", category: "Sprayer Lessons", steps: 4, live: true },
  { id: "booms", name: "Boom Control", category: "Sprayer Lessons", steps: 4, live: false },
]

function operator(over: Partial<Record<string, unknown>> = {}) {
  return {
    id: "sam-patel",
    name: "Sam Patel",
    created_at: "2026-08-07T09:00:00+00:00",
    last_seen: "2026-08-07T09:00:00+00:00",
    onboarded: true,
    turns: 3,
    steps_done: 2,
    steps_total: 8,
    lessons: {
      spray: { done: 2, assigned: true, last_opened: "2026-08-07T09:00:00+00:00" },
      booms: { done: 0, assigned: true, last_opened: null },
    },
    ...over,
  }
}

/** Stand in for Python. The bridge is the only way this screen reaches the
 * outside world, so stubbing it exercises everything the UI actually does. */
function mockBridge(over: Record<string, unknown> = {}) {
  const calls: Array<[string, unknown[]]> = []
  const record = (name: string, result: unknown) =>
    (...args: unknown[]) => {
      calls.push([name, args])
      return Promise.resolve(result)
    }
  window.pywebview = {
    api: {
      admin_overview: record("admin_overview", {
        ok: true,
        lessons: LESSONS,
        operators: [operator()],
        refreshed_at: "2026-08-07T09:30:00+00:00",
      }),
      admin_create_user: record("admin_create_user", {
        ok: true,
        user: null,
        error: null,
      }),
      admin_delete_user: record("admin_delete_user", { ok: true, error: null }),
      admin_set_assignments: record("admin_set_assignments", { ok: true }),
      ...Object.fromEntries(
        Object.entries(over).map(([k, v]) => [k, record(k, v)]),
      ),
    } as never,
  }
  return calls
}

afterEach(() => {
  delete window.pywebview
  vi.restoreAllMocks()
})

describe("AdminScreen", () => {
  it("shows every operator with what they have completed", async () => {
    mockBridge()
    render(<AdminScreen />)
    expect(await screen.findByText("Sam Patel")).toBeDefined()
    expect(screen.getByText(/2 of 8 steps/)).toBeDefined()
  })

  it("counts the roster and the whole cohort's progress", async () => {
    mockBridge()
    render(<AdminScreen />)
    expect(await screen.findByText(/1 person on the roster/)).toBeDefined()
    expect(screen.getByText(/2 of 8 assigned steps complete/)).toBeDefined()
  })

  it("re-reads everyone's progress when refreshed", async () => {
    const calls = mockBridge()
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /refresh progress/i }))
    await waitFor(() =>
      expect(calls.filter(([n]) => n === "admin_overview")).toHaveLength(2),
    )
  })

  it("adds an operator by name", async () => {
    const calls = mockBridge()
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /add operator/i }))
    fireEvent.change(screen.getByPlaceholderText(/their name/i), {
      target: { value: "Ari Reddy" },
    })
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }))
    await waitFor(() =>
      expect(calls.find(([n]) => n === "admin_create_user")?.[1]).toEqual([
        "Ari Reddy",
      ]),
    )
  })

  it("says why a name was refused rather than failing quietly", async () => {
    mockBridge({
      admin_create_user: { ok: false, user: null, error: "Sam Patel is already on the roster" },
    })
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /add operator/i }))
    fireEvent.change(screen.getByPlaceholderText(/their name/i), {
      target: { value: "Sam Patel" },
    })
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }))
    expect(await screen.findByText(/already on the roster/)).toBeDefined()
  })

  it("asks before removing somebody, and says what goes with them", async () => {
    const calls = mockBridge()
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /remove sam patel/i }))
    expect(screen.getByText(/every lesson step they have completed/i)).toBeDefined()
    expect(calls.some(([n]) => n === "admin_delete_user")).toBe(false)
    fireEvent.click(screen.getByRole("button", { name: /^remove$/i }))
    await waitFor(() =>
      expect(calls.find(([n]) => n === "admin_delete_user")?.[1]).toEqual([
        "sam-patel",
      ]),
    )
  })

  it("keeps the operator when the removal is declined", async () => {
    const calls = mockBridge()
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /remove sam patel/i }))
    fireEvent.click(screen.getByRole("button", { name: /keep/i }))
    expect(screen.queryByText(/every lesson step/i)).toBeNull()
    expect(calls.some(([n]) => n === "admin_delete_user")).toBe(false)
  })

  it("sets which lessons an operator works through", async () => {
    const calls = mockBridge()
    render(<AdminScreen />)
    await screen.findByText("Sam Patel")
    fireEvent.click(screen.getByRole("button", { name: /lessons/i }))
    const toggle = screen.getByRole("switch", { name: /spray lesson for sam patel/i })
    expect(toggle.getAttribute("aria-checked")).toBe("true")
    fireEvent.click(toggle)
    await waitFor(() =>
      expect(calls.find(([n]) => n === "admin_set_assignments")?.[1]).toEqual([
        "sam-patel",
        ["booms"],
      ]),
    )
  })

  it("marks an operator who has not been shown the simulator", async () => {
    window.pywebview = {
      api: {
        admin_overview: () =>
          Promise.resolve({
            ok: true,
            lessons: LESSONS,
            operators: [operator({ onboarded: false })],
            refreshed_at: "2026-08-07T09:30:00+00:00",
          }),
      } as never,
    }
    render(<AdminScreen />)
    expect(await screen.findByText(/has not started yet/i)).toBeDefined()
  })
})
