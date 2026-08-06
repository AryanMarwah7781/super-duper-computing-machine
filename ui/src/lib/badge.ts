/**
 * Draws an ID badge as a data URL, for the front face of a hanging lanyard.
 *
 * The Lanyard component takes a `frontImage` URL, so each operator gets their
 * own card without touching the 3D model or shipping a texture per person.
 *
 * The card art is 512x768 to match the model's front-face aspect; anything
 * squarer gets letterboxed by `imageFit`.
 */

const BRAND = "#004884"
const W = 512
const H = 768

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("")
}

/** Shrink the font until the name fits the card width. */
function fitText(ctx: CanvasRenderingContext2D, text: string, max: number) {
  let size = 62
  do {
    ctx.font = `600 ${size}px "Geist Variable", system-ui, sans-serif`
    size -= 2
  } while (ctx.measureText(text).width > max && size > 24)
}

export function makeBadge(name: string, subtitle = "OPERATOR"): string {
  const canvas = document.createElement("canvas")
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext("2d")
  if (!ctx) return ""

  ctx.fillStyle = "#ffffff"
  ctx.fillRect(0, 0, W, H)

  // Brand header band
  ctx.fillStyle = BRAND
  ctx.fillRect(0, 0, W, 176)
  ctx.fillStyle = "rgba(255,255,255,0.92)"
  ctx.font = '700 30px "Geist Variable", system-ui, sans-serif'
  ctx.textAlign = "center"
  ctx.fillText("DEERE ASSIST", W / 2, 74)
  ctx.font = '500 22px "Geist Variable", system-ui, sans-serif'
  ctx.fillStyle = "rgba(255,255,255,0.72)"
  ctx.fillText("R4045 SPRAYER", W / 2, 116)

  // Portrait plate with initials — no photos exist, so initials stand in
  ctx.fillStyle = "#eef2f6"
  roundRect(ctx, W / 2 - 108, 232, 216, 216, 24)
  ctx.fill()
  ctx.fillStyle = BRAND
  ctx.font = '700 92px "Geist Variable", system-ui, sans-serif'
  ctx.textBaseline = "middle"
  ctx.fillText(initials(name) || "?", W / 2, 344)
  ctx.textBaseline = "alphabetic"

  // Name
  ctx.fillStyle = "#0b0b0d"
  fitText(ctx, name, W - 72)
  ctx.fillText(name, W / 2, 546)

  ctx.fillStyle = "#6b7280"
  ctx.font = '500 24px "Geist Variable", system-ui, sans-serif'
  ctx.fillText(subtitle, W / 2, 590)

  // Footer rule + credit
  ctx.strokeStyle = "#e5e7eb"
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(56, 654)
  ctx.lineTo(W - 56, 654)
  ctx.stroke()
  ctx.fillStyle = "#9ca3af"
  ctx.font = '600 20px "Geist Variable", system-ui, sans-serif'
  ctx.fillText("L&T  ×  CNH", W / 2, 700)

  return canvas.toDataURL("image/png")
}

/** The blank badge on the spare lanyard — the one a new person takes. */
export function makeBlankBadge(): string {
  const canvas = document.createElement("canvas")
  canvas.width = W
  canvas.height = H
  const ctx = canvas.getContext("2d")
  if (!ctx) return ""

  ctx.fillStyle = "#ffffff"
  ctx.fillRect(0, 0, W, H)
  ctx.fillStyle = BRAND
  ctx.fillRect(0, 0, W, 176)
  ctx.fillStyle = "rgba(255,255,255,0.92)"
  ctx.font = '700 30px "Geist Variable", system-ui, sans-serif'
  ctx.textAlign = "center"
  ctx.fillText("DEERE ASSIST", W / 2, 74)
  ctx.font = '500 22px "Geist Variable", system-ui, sans-serif'
  ctx.fillStyle = "rgba(255,255,255,0.72)"
  ctx.fillText("R4045 SPRAYER", W / 2, 116)

  // Empty plate: dashed, to read as unissued rather than broken
  ctx.setLineDash([12, 10])
  ctx.strokeStyle = "#c7ccd1"
  ctx.lineWidth = 4
  roundRect(ctx, W / 2 - 108, 232, 216, 216, 24)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.fillStyle = "#c7ccd1"
  ctx.font = '300 110px "Geist Variable", system-ui, sans-serif'
  ctx.textBaseline = "middle"
  ctx.fillText("+", W / 2, 340)
  ctx.textBaseline = "alphabetic"

  ctx.fillStyle = "#0b0b0d"
  ctx.font = '600 46px "Geist Variable", system-ui, sans-serif'
  ctx.fillText("New operator", W / 2, 546)
  ctx.fillStyle = "#6b7280"
  ctx.font = '500 24px "Geist Variable", system-ui, sans-serif'
  ctx.fillText("TAP TO SIGN IN", W / 2, 590)

  ctx.strokeStyle = "#e5e7eb"
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(56, 654)
  ctx.lineTo(W - 56, 654)
  ctx.stroke()
  ctx.fillStyle = "#9ca3af"
  ctx.font = '600 20px "Geist Variable", system-ui, sans-serif'
  ctx.fillText("L&T  ×  CNH", W / 2, 700)

  return canvas.toDataURL("image/png")
}
