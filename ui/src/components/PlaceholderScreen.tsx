import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"

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
    <div className="flex h-full items-center justify-center px-8">
      <Empty className="max-w-xl">
        <EmptyHeader>
          <EmptyMedia>
            <Art className="h-48 text-primary" />
          </EmptyMedia>
          <EmptyTitle className="text-3xl">{title}</EmptyTitle>
          <EmptyDescription className="text-lg">{blurb}</EmptyDescription>
        </EmptyHeader>
        <EmptyContent>
          <p className="text-sm text-muted-foreground">
            No content is wired up here yet — the screen and its navigation are
            ready for it.
          </p>
          <Button variant="outline" className="mt-4" onClick={onHome}>
            Back to the menu
          </Button>
        </EmptyContent>
      </Empty>
    </div>
  )
}
