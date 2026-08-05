/**
 * Names the collaboration in type only.
 *
 * These are wordmarks set in the app's own typeface, not reproductions of
 * either company's logo — the real marks should replace this once the brand
 * assets are to hand.
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
