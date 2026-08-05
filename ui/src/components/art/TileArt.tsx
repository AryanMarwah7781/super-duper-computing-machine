/**
 * Artwork for the three home tiles.
 *
 * Inline SVG rather than raster images: it stays crisp at any window size, adds
 * nothing to the bundle beyond its own markup, and inherits the theme — strokes
 * use currentColor and fills use the shadcn palette variables, so light and dark
 * both work without a second set of assets.
 */

type ArtProps = { className?: string }

const STROKE = {
  stroke: "currentColor",
  strokeWidth: 2.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  fill: "none",
}

/** A soft backdrop so each tile reads as an illustration, not a bare icon. */
function Blob({ d }: { d: string }) {
  return <path d={d} className="fill-primary/10" />
}

export function LessonPlanArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 240 180" className={className} role="img"
         aria-label="An open book with a checklist and a graduation cap">
      <Blob d="M52 96c-14-38 10-72 52-76s76 14 84 48-8 66-44 78-78 -12-92-50Z" />

      {/* open book */}
      <path {...STROKE}
            d="M120 66C106 55 86 50 62 53v82c24-3 44 2 58 13" />
      <path {...STROKE}
            d="M120 66c14-11 34-16 58-13v82c-24-3-44 2-58 13" />
      <path {...STROKE} d="M120 66v82" />

      {/* checklist on the left page */}
      <path {...STROKE} strokeWidth={2} d="M74 76l5 5 9-10" />
      <path {...STROKE} strokeWidth={2} d="M74 96l5 5 9-10" />
      <path {...STROKE} strokeWidth={2} className="opacity-40"
            d="M74 116h14" />
      <path {...STROKE} strokeWidth={2} className="opacity-70"
            d="M96 78h12M96 98h10M96 118h14" />

      {/* text lines on the right page */}
      <path {...STROKE} strokeWidth={2} className="opacity-70"
            d="M134 78h34M134 92h28M134 106h34M134 120h22" />

      {/* graduation cap */}
      <path {...STROKE} className="fill-primary/20"
            d="M120 18l30 13-30 13-30-13 30-13Z" />
      <path {...STROKE} d="M142 37v14c0 6-10 10-22 10s-22-4-22-10V37" />
      <path {...STROKE} d="M152 31v18" />
    </svg>
  )
}

export function ChatbotArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 240 180" className={className} role="img"
         aria-label="Speech bubbles with a voice waveform">
      <Blob d="M44 88c0-40 30-70 76-70s76 26 76 68-26 74-76 74S44 128 44 88Z" />

      {/* trailing bubble */}
      <path {...STROKE} className="opacity-40"
            d="M62 46h44a10 10 0 0 1 10 10v20a10 10 0 0 1-10 10H62a10 10 0 0 1-10-10V56a10 10 0 0 1 10-10Z" />

      {/* main bubble with tail */}
      <path {...STROKE} className="fill-card"
            d="M108 62h64a14 14 0 0 1 14 14v42a14 14 0 0 1-14 14h-40l-20 18v-18h-4a14 14 0 0 1-14-14V76a14 14 0 0 1 14-14Z" />

      {/* waveform — the bars say "voice", not "type" */}
      <path {...STROKE} d="M124 90v14" />
      <path {...STROKE} d="M138 82v30" />
      <path {...STROKE} d="M152 74v46" />
      <path {...STROKE} d="M166 84v26" />
      <path {...STROKE} d="M180 92v10" />

      {/* sparkles */}
      <path {...STROKE} strokeWidth={2} className="opacity-60"
            d="M196 46l3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z" />
      <circle cx={54} cy={118} r={4} className="fill-primary/40" />
    </svg>
  )
}

/**
 * The hero mark for the chat welcome: a self-propelled sprayer in the field.
 *
 * The screen says "let's start farming", so the mark should show the machine —
 * a speech bubble describes the interface, not the work.
 */
export function FarmingHeroArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 240 180" className={className} role="img"
         aria-label="A self-propelled sprayer with its boom extended, spraying a field">
      <circle cx={120} cy={84} r={70} className="fill-primary/10" />

      {/* sun */}
      <circle cx={194} cy={34} r={10} {...STROKE} strokeWidth={2}
              className="fill-primary/20" />
      <path {...STROKE} strokeWidth={2} className="opacity-40"
            d="M194 16v5M194 47v5M176 34h5M207 34h5M181 21l4 4M203 43l4 4M207 21l-4 4M185 43l-4 4" />

      {/* spray, furthest back: mist falling from each nozzle */}
      <g className="fill-current opacity-20">
        <path d="M38 100l8 22h-16Z" />
        <path d="M58 100l8 22h-16Z" />
        <path d="M78 100l8 22h-16Z" />
        <path d="M162 100l8 22h-16Z" />
        <path d="M182 100l8 22h-16Z" />
        <path d="M202 100l8 22h-16Z" />
      </g>

      {/* boom — drawn before the machine, so the body occludes its middle */}
      <path {...STROKE} d="M26 94h188" />
      <path {...STROKE} strokeWidth={2}
            d="M38 94v6M58 94v6M78 94v6M162 94v6M182 94v6M202 94v6" />

      {/* tank, with its fill hatch */}
      <path {...STROKE} className="fill-card"
            d="M74 68h56a10 10 0 0 1 10 10v28H74a8 8 0 0 1-8-8V76a8 8 0 0 1 8-8Z" />
      <path {...STROKE} strokeWidth={2} d="M92 68v-6h14v6" />
      <path {...STROKE} strokeWidth={2} className="opacity-30" d="M78 96h34" />

      {/* cab */}
      <path {...STROKE} className="fill-card"
            d="M140 54h24a10 10 0 0 1 10 10v42h-34V54Z" />
      <path {...STROKE} strokeWidth={2} className="fill-primary/15"
            d="M147 62h20v18h-20V62Z" />

      {/* the high clearance that says sprayer rather than truck */}
      <path {...STROKE} d="M84 106v12M162 106v12" />

      {/* wheels, sitting on the ground */}
      <circle cx={84} cy={132} r={17} {...STROKE} className="fill-card" />
      <circle cx={84} cy={132} r={6} {...STROKE} strokeWidth={2} />
      <circle cx={162} cy={132} r={17} {...STROKE} className="fill-card" />
      <circle cx={162} cy={132} r={6} {...STROKE} strokeWidth={2} />

      <path {...STROKE} d="M22 150h196" />

      {/* crop rows: quiet stubble, so it does not compete with the spray */}
      <path {...STROKE} strokeWidth={2} className="opacity-30"
            d="M32 150v-7M44 150v-5M56 150v-8M68 150v-5
               M176 150v-5M188 150v-8M200 150v-5M212 150v-7" />
    </svg>
  )
}

export function SimulatorArt({ className }: ArtProps) {
  return (
    <svg viewBox="0 0 240 180" className={className} role="img"
         aria-label="A monitor showing a sprayer, with a play button">
      <Blob d="M40 92c0-42 34-74 80-74s80 30 80 72-34 68-80 68-80-24-80-66Z" />

      {/* monitor */}
      <path {...STROKE} className="fill-card"
            d="M52 40h136a10 10 0 0 1 10 10v72a10 10 0 0 1-10 10H52a10 10 0 0 1-10-10V50a10 10 0 0 1 10-10Z" />
      <path {...STROKE} d="M104 132v14h32v-14" />
      <path {...STROKE} d="M88 150h64" />

      {/* field horizon and sun */}
      <path {...STROKE} strokeWidth={2} className="opacity-50" d="M56 106h128" />
      <circle cx={168} cy={62} r={9} {...STROKE} strokeWidth={2}
              className="fill-primary/20 opacity-70" />

      {/* sprayer: boom, body, wheels */}
      <path {...STROKE} strokeWidth={2} d="M62 84h116" />
      <path {...STROKE} strokeWidth={2} className="opacity-60"
            d="M74 84v7M90 84v7M150 84v7M166 84v7" />
      <path {...STROKE} className="fill-primary/20"
            d="M104 70h26l8 14h-42l8-14Z" />
      <circle cx={108} cy={98} r={8} {...STROKE} />
      <circle cx={136} cy={98} r={6} {...STROKE} />

      {/* play button */}
      <circle cx={188} cy={124} r={20} {...STROKE} className="fill-primary/15" />
      <path {...STROKE} className="fill-current"
            d="M183 116l14 8-14 8v-16Z" />
    </svg>
  )
}
