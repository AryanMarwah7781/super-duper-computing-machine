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

  it("rejoins a step that the corpus wrapped mid-sentence", () => {
    // Seen on screen: step 2 rendered as two separate paragraphs.
    const text =
      "Step 2: Fill the tank about half full with clean, clear water, or\n" +
      "other base liquid.\n" +
      "Step 3: Add the chemical concentrate."
    const nodes = parseDisplayText(text, [])
    expect(nodes).toHaveLength(2)
    expect(nodes[0]).toEqual({
      kind: "step",
      num: "2",
      text: "Fill the tank about half full with clean, clear water, or other base liquid.",
    })
  })

  it("does not swallow a following safety line into the step", () => {
    const nodes = parseDisplayText(
      "Step 1: Park the machine.\n**CAUTION:** Do not overfill.",
      [],
    )
    expect(nodes.map((n) => n.kind)).toEqual(["step", "safety"])
  })

  it("does not swallow a following photo marker into the step", () => {
    const nodes = parseDisplayText(
      "Step 1: Open the lid.\n[PHOTO: N99948—UN—17SEP12]",
      [],
    )
    expect(nodes.map((n) => n.kind)).toEqual(["step", "photo"])
  })

  it("leaves prose before any step as its own paragraph", () => {
    const nodes = parseDisplayText("Here's how:\nStep 1: Go.", [])
    expect(nodes.map((n) => n.kind)).toEqual(["text", "step"])
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

describe("PDF hard-wrapping", () => {
  // Verbatim from the board, 2026-08-10, "how do i start spraying". The corpus
  // carries the manual's column line breaks, so one sentence arrives as five
  // physical lines.
  const WRAPPED = [
    "**CAUTION:** Do not turn on the machine until you",
    "are sure that nobody is in the danger zone.",
    "NOTE: Plungers do not open properly when operating",
    "above 965.3 kPa (9.65 bar) (140 psi) when a low",
    "voltage condition occurs.",
    "Operate Indexed Boom Sections (IBS)",
    "This machine is equipped with Indexed Boom Section",
    "(IBS) switching. This gives the operator another way to",
    "shutoff boom spray sections in sequence without",
    "removing your hand from the multi-function lever.",
  ].join("\n")

  const SAFETY_BLOCKS = [
    {
      level: "CAUTION",
      text:
        "Do not turn on the machine until you\nare sure that nobody is in the " +
        "danger zone.\nNOTE: Plungers do not open properly when operating\n" +
        "above 965.3 kPa (9.65 bar) (140 psi) when a low\nvoltage condition occurs.",
    },
  ]

  it("keeps a wrapped warning whole instead of cutting it mid-sentence", () => {
    const nodes = parseDisplayText(WRAPPED, [], SAFETY_BLOCKS)
    const safety = nodes.find((n) => n.kind === "safety")!
    expect(safety.text).toContain("nobody is in the danger zone")
    expect(safety.text).toContain("voltage condition occurs")
  })

  it("does not leak the rest of the warning into the body", () => {
    const nodes = parseDisplayText(WRAPPED, [], SAFETY_BLOCKS)
    const body = nodes.filter((n) => n.kind === "text").map((n) => n.text)
    expect(body.join(" ")).not.toContain("danger zone")
  })

  it("stops the warning where the manual stops it", () => {
    // The line after the block is new content and must not be swallowed.
    const nodes = parseDisplayText(WRAPPED, [], SAFETY_BLOCKS)
    const safety = nodes.find((n) => n.kind === "safety")!
    expect(safety.text).not.toContain("Indexed Boom Sections")
    expect(nodes.some((n) => n.kind === "text" && n.text.includes("Indexed Boom Section"))).toBe(true)
  })

  it("joins wrapped body lines into one paragraph", () => {
    const nodes = parseDisplayText(WRAPPED, [], SAFETY_BLOCKS)
    const body = nodes.filter((n) => n.kind === "text")
    const joined = body.map((n) => n.text).join(" ")
    expect(joined).toContain("This machine is equipped with Indexed Boom Section (IBS) switching")
    expect(body.length).toBeLessThan(4)
  })

  it("still works when no safety blocks are supplied", () => {
    const nodes = parseDisplayText(WRAPPED, [])
    expect(nodes.find((n) => n.kind === "safety")!.level).toBe("CAUTION")
  })

  it("keeps separate paragraphs separate", () => {
    const nodes = parseDisplayText("First para wraps\nover two lines.\n\nSecond para.", [])
    const body = nodes.filter((n) => n.kind === "text")
    expect(body).toHaveLength(2)
    expect(body[0].text).toBe("First para wraps over two lines.")
  })
})
