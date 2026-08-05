import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useNavigation } from "./useNavigation"

describe("useNavigation", () => {
  it("starts on the login screen with no history", () => {
    const { result } = renderHook(() => useNavigation())
    expect(result.current.screen).toBe("login")
    expect(result.current.canGoBack).toBe(false)
    expect(result.current.canGoForward).toBe(false)
  })

  it("goes forward to a new screen", () => {
    const { result } = renderHook(() => useNavigation())
    act(() => result.current.go("home"))
    expect(result.current.screen).toBe("home")
    expect(result.current.canGoBack).toBe(true)
  })

  it("walks back and forward again", () => {
    const { result } = renderHook(() => useNavigation())
    act(() => result.current.go("home"))
    act(() => result.current.go("chat"))
    act(() => result.current.back())
    expect(result.current.screen).toBe("home")
    expect(result.current.canGoForward).toBe(true)
    act(() => result.current.forward())
    expect(result.current.screen).toBe("chat")
  })

  it("truncates the forward branch when navigating somewhere new", () => {
    const { result } = renderHook(() => useNavigation())
    act(() => result.current.go("home"))
    act(() => result.current.go("chat"))
    act(() => result.current.back())
    act(() => result.current.go("simulator"))
    expect(result.current.screen).toBe("simulator")
    expect(result.current.canGoForward).toBe(false)
  })

  it("cannot walk back past the first screen", () => {
    const { result } = renderHook(() => useNavigation())
    act(() => result.current.back())
    expect(result.current.screen).toBe("login")
    expect(result.current.canGoBack).toBe(false)
  })

  it("reset forgets the trail so the next person cannot walk back in", () => {
    const { result } = renderHook(() => useNavigation())
    act(() => result.current.go("home"))
    act(() => result.current.go("chat"))
    act(() => result.current.reset())
    expect(result.current.screen).toBe("login")
    expect(result.current.canGoBack).toBe(false)
    expect(result.current.canGoForward).toBe(false)
  })
})
