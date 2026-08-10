/**
 * Parses the fixed line grammar emitted by v4's render.py.
 *
 * This is a PURE function and the only place the grammar is known. It does not
 * re-derive an answer — render.py already did that, and its output is the
 * Tier-0 verified artefact. This turns those lines into nodes a React tree can
 * style.
 *
 * Order matters: a safety line and a heading both start with `**`, so safety is
 * tested first.
 */

export type ImageRef = {
  id_code: string
  image_path: string
  caption: string
  step_num: number | null
}

export type Node =
  | { kind: "safety"; level: string; text: string }
  | { kind: "step"; num: string; text: string }
  | { kind: "photo"; caption: string; image: ImageRef | null }
  | { kind: "row"; cells: string[] }
  | { kind: "citation"; page: string }
  | { kind: "heading"; text: string }
  | { kind: "text"; text: string }

const SAFETY = /^\*\*(DANGER|WARNING|CAUTION|NOTE|IMPORTANT):\*\*\s*(.*)$/
const STEP = /^Step\s+(\S+):\s*(.*)$/
const PHOTO = /^\[PHOTO:\s*(.*?)\]$/
const CITATION = /^_Manual page\s+(\d+)\._$/
const HEADING = /^\*\*(.+?)\*\*$/

/**
 * render.py emits `[PHOTO: {caption}]`, where caption falls back to the id code
 * and then to "figure" — so markers are matched on caption first, id code
 * second. An unmatched marker becomes its own caption text rather than a broken
 * image icon.
 */
function findImage(caption: string, images: ImageRef[]): ImageRef | null {
  return (
    images.find((i) => i.caption === caption) ??
    images.find((i) => i.id_code === caption) ??
    null
  )
}

export type SafetyRef = { level: string; text: string }

export function parseDisplayText(
  displayText: string,
  images: ImageRef[],
  safetyBlocks: SafetyRef[] = [],
): Node[] {
  const nodes: Node[] = []

  /**
   * How many more physical lines belong to the warning just emitted.
   *
   * The corpus keeps the manual's column line breaks, so one warning arrives
   * as several lines — "Do not turn on the machine until you" / "are sure that
   * nobody is in the danger zone." Matching only the first left the banner cut
   * mid-sentence and spilled the rest into the body as loose paragraphs.
   *
   * The count comes from the answer's own `safety` block rather than from
   * guessing where the warning ends, because the line after it is ordinary
   * content that must not be swallowed.
   */
  let safetyRemaining = 0

  /**
   * The corpus wraps mid-sentence, so a step's text arrives across several
   * lines. Without this, "Fill the tank about half full with clean, clear
   * water, or" and "other base liquid." render as two separate paragraphs and
   * the step looks broken. A plain line following a step belongs to that step.
   */
  const continueLastStep = (text: string): boolean => {
    const last = nodes[nodes.length - 1]
    if (!last || last.kind !== "step") return false
    last.text = `${last.text} ${text}`.replace(/\s+/g, " ").trim()
    return true
  }

  /** Same wrapping problem, applied to prose. A blank line ends a paragraph. */
  const continueLastParagraph = (text: string): boolean => {
    const last = nodes[nodes.length - 1]
    if (!last || last.kind !== "text" || paragraphBroken) return false
    last.text = `${last.text} ${text}`.replace(/\s+/g, " ").trim()
    return true
  }

  let paragraphBroken = true

  for (const raw of displayText.split("\n")) {
    const line = raw.trim()
    if (!line) {
      // A blank line is the only paragraph separator the grammar has.
      paragraphBroken = true
      continue
    }

    if (safetyRemaining > 0) {
      safetyRemaining -= 1
      continue
    }

    const safety = SAFETY.exec(line)
    if (safety) {
      const block = safetyBlocks.find(
        (b) => b.level === safety[1] && b.text.startsWith(safety[2]),
      )
      const text = (block?.text ?? safety[2]).replace(/\s+/g, " ").trim()
      // Skip the remaining physical lines this warning occupies, so they are
      // not re-emitted as body text below the banner.
      safetyRemaining = block ? block.text.split("\n").length - 1 : 0
      nodes.push({ kind: "safety", level: safety[1], text })
      paragraphBroken = true
      continue
    }

    const step = STEP.exec(line)
    if (step) {
      nodes.push({ kind: "step", num: step[1], text: step[2] })
      paragraphBroken = true
      continue
    }

    const photo = PHOTO.exec(line)
    if (photo) {
      const caption = photo[1]
      nodes.push({ kind: "photo", caption, image: findImage(caption, images) })
      paragraphBroken = true
      continue
    }

    const citation = CITATION.exec(line)
    if (citation) {
      nodes.push({ kind: "citation", page: citation[1] })
      paragraphBroken = true
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      nodes.push({ kind: "heading", text: heading[1] })
      paragraphBroken = true
      continue
    }

    if (line.includes(" | ")) {
      nodes.push({
        kind: "row",
        cells: line
          .split("|")
          .map((c) => c.trim())
          .filter(Boolean),
      })
      paragraphBroken = true
      continue
    }

    if (!continueLastStep(line) && !continueLastParagraph(line)) {
      nodes.push({ kind: "text", text: line })
      paragraphBroken = false
    }
  }

  return nodes
}

/** Images are served by the local bundle server, never straight from the devkit. */
export function imageUrl(image: ImageRef): string {
  const rel = image.image_path || image.id_code
  return `/images/${rel.replace(/^images\//, "")}`
}
