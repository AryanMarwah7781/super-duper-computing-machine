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

export function parseDisplayText(
  displayText: string,
  images: ImageRef[],
): Node[] {
  const nodes: Node[] = []

  for (const raw of displayText.split("\n")) {
    const line = raw.trim()
    if (!line) continue

    const safety = SAFETY.exec(line)
    if (safety) {
      nodes.push({ kind: "safety", level: safety[1], text: safety[2] })
      continue
    }

    const step = STEP.exec(line)
    if (step) {
      nodes.push({ kind: "step", num: step[1], text: step[2] })
      continue
    }

    const photo = PHOTO.exec(line)
    if (photo) {
      const caption = photo[1]
      nodes.push({ kind: "photo", caption, image: findImage(caption, images) })
      continue
    }

    const citation = CITATION.exec(line)
    if (citation) {
      nodes.push({ kind: "citation", page: citation[1] })
      continue
    }

    const heading = HEADING.exec(line)
    if (heading) {
      nodes.push({ kind: "heading", text: heading[1] })
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
      continue
    }

    nodes.push({ kind: "text", text: line })
  }

  return nodes
}

/** Images are served by the local bundle server, never straight from the devkit. */
export function imageUrl(image: ImageRef): string {
  const rel = image.image_path || image.id_code
  return `/images/${rel.replace(/^images\//, "")}`
}
