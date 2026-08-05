import { describe, expect, it } from "vitest"
import { imageUrl, parseDisplayText, type ImageRef } from "./render"

const IMAGES: ImageRef[] = [
  {
    id_code: "N136007—UN—05MAR18",
    image_path: "images/fill_cap.png",
    caption: "Fill cap location",
    step_num: 2,
  },
]

describe("parseDisplayText", () => {
  it("parses a safety line into a safety node", () => {
    const [node] = parseDisplayText("**WARNING:** Keep clear.", [])
    expect(node).toEqual({ kind: "safety", level: "WARNING", text: "Keep clear." })
  })

  it("parses CAUTION and DANGER too", () => {
    expect(parseDisplayText("**CAUTION:** Slow.", [])[0].kind).toBe("safety")
    expect(parseDisplayText("**DANGER:** Stop.", [])[0].kind).toBe("safety")
  })

  it("parses a numbered step", () => {
    const [node] = parseDisplayText("Step 3: Fill the tank.", [])
    expect(node).toEqual({ kind: "step", num: "3", text: "Fill the tank." })
  })

  it("resolves a photo marker against images by caption", () => {
    const [node] = parseDisplayText("[PHOTO: Fill cap location]", IMAGES)
    expect(node.kind).toBe("photo")
    expect(node).toMatchObject({ image: IMAGES[0] })
  })

  it("keeps a photo marker with no matching image as text, not a broken image", () => {
    const [node] = parseDisplayText("[PHOTO: Nothing here]", IMAGES)
    expect(node).toEqual({ kind: "photo", caption: "Nothing here", image: null })
  })

  it("parses a table row", () => {
    const [node] = parseDisplayText("380/90R46 | 240 kPa | 3200 kg", [])
    expect(node).toEqual({
      kind: "row",
      cells: ["380/90R46", "240 kPa", "3200 kg"],
    })
  })

  it("parses the citation footer", () => {
    const [node] = parseDisplayText("_Manual page 472._", [])
    expect(node).toEqual({ kind: "citation", page: "472" })
  })

  it("parses a bold heading, and does not mistake it for safety", () => {
    const [node] = parseDisplayText("**Tire Inflation Pressure**", [])
    expect(node).toEqual({ kind: "heading", text: "Tire Inflation Pressure" })
  })

  it("skips blank lines", () => {
    expect(parseDisplayText("Step 1: A.\n\n\nStep 2: B.", [])).toHaveLength(2)
  })

  it("parses the full procedure fixture in order, safety first", () => {
    const text = [
      "**WARNING:** Keep bystanders clear of the machine while filling.",
      "Step 1: Park the machine on a level surface and shut off the engine.",
      "Step 2: Open the fill cap (A: Fill Cap).",
      "[PHOTO: Fill cap location]",
      "Step 3: Fill the solution tank to the required level.",
      "**CAUTION:** Do not overfill the tank.",
      "",
      "_Manual page 472._",
    ].join("\n")
    const nodes = parseDisplayText(text, IMAGES)
    expect(nodes.map((n) => n.kind)).toEqual([
      "safety",
      "step",
      "step",
      "photo",
      "step",
      "safety",
      "citation",
    ])
  })
})

describe("imageUrl", () => {
  it("maps an image_path onto the local bundle server", () => {
    expect(imageUrl(IMAGES[0])).toBe("/images/fill_cap.png")
  })

  it("falls back to the id code when there is no path", () => {
    expect(imageUrl({ ...IMAGES[0], image_path: "" })).toBe(
      "/images/N136007—UN—05MAR18",
    )
  })
})
