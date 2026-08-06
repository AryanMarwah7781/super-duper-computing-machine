import logo from "@/assets/ltts-stacked.png"

/**
 * The real L&T Technology Services stacked lockup, used as supplied.
 *
 * The logo is a single ink colour, #004884, sampled from the file itself —
 * that is the value the theme's --primary is set to, so the UI and the mark
 * agree rather than approximately matching.
 *
 * On dark backgrounds the artwork is inverted-safe only down to a point, so it
 * sits on a light plate there instead of being recoloured. Never restyle a
 * supplied brand mark.
 */
export function LttsLogo({ className }: { className?: string }) {
  return (
    <img
      src={logo}
      alt="L&T Technology Services"
      className={className}
      draggable={false}
    />
  )
}

/**
 * Names the collaboration in type.
 *
 * Deliberately not the logo artwork: the stacked lockup carries a wordmark, so
 * at the size this sits at the words are unreadable — and the screens that show
 * this already show the real mark elsewhere. Shrinking a supplied logo past
 * legibility is worse than setting the name in type.
 */
export function CollaborationMark({ className }: { className?: string }) {
  return (
    <div className={`flex flex-col items-center gap-2 ${className ?? ""}`}>
      <div className="flex items-center gap-4">
        <span className="h-px w-10 bg-border" />
        <span className="flex items-baseline gap-3">
          <span className="text-base font-bold tracking-tight">{"L&T"}</span>
          <span className="text-xs text-muted-foreground">×</span>
          <span className="text-base font-bold tracking-tight">CNH</span>
        </span>
        <span className="h-px w-10 bg-border" />
      </div>
      <span className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
        Collaboration
      </span>
    </div>
  )
}
