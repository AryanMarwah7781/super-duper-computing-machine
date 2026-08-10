import { fireEvent, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { SimulatorScreen } from "./SimulatorScreen"

function mockVideo(available: boolean, path = "C:\\Videos\\starter.mp4") {
  window.pywebview = {
    api: {
      starter_video: () =>
        Promise.resolve({ url: "/media/starter.mp4", available, path }),
    } as never,
  }
}

afterEach(() => {
  delete window.pywebview
  vi.restoreAllMocks()
})

describe("SimulatorScreen", () => {
  it("plays the walkthrough recording", async () => {
    mockVideo(true)
    const { container } = render(<SimulatorScreen onDone={() => {}} />)
    await screen.findByText(/start the connections app/i)
    const video = await vi.waitFor(() => {
      const el = container.querySelector("video")
      if (!el) throw new Error("no video yet")
      return el
    })
    expect(video.getAttribute("src")).toBe("/media/starter.mp4")
  })

  it("says where the recording should be rather than showing a dead player", async () => {
    mockVideo(false)
    const { container } = render(<SimulatorScreen onDone={() => {}} />)
    expect(await screen.findByText(/recording is missing/i)).toBeDefined()
    expect(screen.getByText(/C:\\Videos\\starter.mp4/)).toBeDefined()
    expect(container.querySelector("video")).toBeNull()
  })

  it("greets a brand new operator by name", async () => {
    mockVideo(true)
    render(<SimulatorScreen firstRun userName="Ari Reddy" onDone={() => {}} />)
    expect(await screen.findByText(/welcome, ari/i)).toBeDefined()
  })

  it("is the same screen from the menu, without the welcome", async () => {
    mockVideo(true)
    render(<SimulatorScreen userName="Ari Reddy" onDone={() => {}} />)
    expect(await screen.findByText("Start the simulator")).toBeDefined()
    expect(screen.queryByText(/welcome, ari/i)).toBeNull()
  })

  it("hands the operator on when they are ready", async () => {
    mockVideo(true)
    const onDone = vi.fn()
    render(<SimulatorScreen firstRun userName="Ari" onDone={onDone} />)
    fireEvent.click(await screen.findByRole("button", { name: /take me in/i }))
    expect(onDone).toHaveBeenCalled()
  })
})
