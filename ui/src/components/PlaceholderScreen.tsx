import { Button } from "@/components/ui/button"

/**
 * Lesson Plan and the simulator guide have no content behind them yet. This
 * says so plainly rather than showing an empty shell that looks broken — and
 * it keeps both routes real, so navigation and the back/forward pair are
 * exercised end to end.
 */
export function PlaceholderScreen({
  title,
  blurb,
  Art,
  onHome,
}: {
  title: string
  blurb: string
  Art: (p: { className?: string }) => React.ReactElement
  onHome: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-8 text-center">
      <Art className="h-56 text-primary" />
      <h1 className="mt-6 text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-3 max-w-lg text-lg text-muted-foreground">{blurb}</p>
      <p className="mt-6 max-w-md text-sm text-muted-foreground">
        No content is wired up here yet — the screen and its navigation are
        ready for it.
      </p>
      <Button variant="outline" className="mt-8" onClick={onHome}>
        Back to the menu
      </Button>
    </div>
  )
}
