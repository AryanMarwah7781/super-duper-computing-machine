import { useEffect } from "react"
import { ChevronRight } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useLessons } from "@/hooks/useLessons"
import { closeLesson, type LessonDto, type LessonRecord } from "@/lib/bridge"
import { LessonDetail, ProgressBar } from "./LessonDetail"

/** "Today 14:32" / "Yesterday" / "4 Aug" — short enough for a card footer. */
function when(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  const days = Math.round(
    (new Date().setHours(0, 0, 0, 0) - new Date(at).setHours(0, 0, 0, 0)) /
      86_400_000,
  )
  if (days === 0) {
    return `today ${at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
  }
  if (days === 1) return "yesterday"
  return at.toLocaleDateString([], { day: "numeric", month: "short" })
}

function status(lesson: LessonDto, record?: LessonRecord): string {
  const total = lesson.steps.length
  const done = record?.steps_done.length ?? 0
  if (done >= total && total > 0) return `All ${total} steps complete`
  if (done > 0) return `${done} of ${total} steps complete`
  if (record?.last_opened) return `Opened ${when(record.last_opened)}`
  return "Not started"
}

function LessonCard({
  lesson,
  record,
  onOpen,
}: {
  lesson: LessonDto
  record?: LessonRecord
  onOpen: () => void
}) {
  const total = lesson.steps.length
  const done = record?.steps_done.length ?? 0
  // A lesson is live-synced when its steps are wired to signals from the
  // armrest. The rest are performed in Farming Simulator, which tells us
  // nothing — those are ticked off by hand, and the card says so up front.
  const live = lesson.steps.some((s) => s.sync)

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex flex-col rounded-2xl border bg-card p-6 text-left
                 transition hover:-translate-y-1 hover:border-primary/40
                 hover:shadow-lg focus-visible:outline-none
                 focus-visible:ring-2 focus-visible:ring-ring"
    >
      <div className="flex items-start gap-3">
        <h3 className="flex-1 text-xl font-semibold">{lesson.name}</h3>
        <ChevronRight className="mt-1 size-5 shrink-0 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
      </div>

      <Badge variant="secondary" className="mt-3">
        {live ? "On the CommandARM" : "In Farming Simulator"}
      </Badge>

      {lesson.summary && (
        <p className="mt-3 line-clamp-3 text-muted-foreground">{lesson.summary}</p>
      )}

      <div className="mt-6 flex-1" />
      <ProgressBar done={done} total={total} />
      <p className="mt-2 text-sm text-muted-foreground">
        {status(lesson, record)}
      </p>
    </button>
  )
}

export function LessonScreen({
  userId,
  onHome,
}: {
  userId: string
  onHome: () => void
}) {
  const { categories, progress, open, done, loading, select, close, tick, restart } =
    useLessons(userId)

  // Leaving the screen entirely — signing out, or the menu — must stop the
  // log being watched. Nothing here would show a step completing.
  useEffect(() => () => void closeLesson(), [])

  if (open) {
    return (
      <LessonDetail
        open={open}
        done={done}
        onBack={() => void close()}
        onTick={(index) => void tick(index)}
        onRestart={() => void restart()}
      />
    )
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">
          Pick a lesson
        </h1>
        <p className="mt-2 text-lg text-muted-foreground">
          Each one is a short procedure on the machine. Where the CommandARM
          reports back, steps tick themselves off as you work the console.
        </p>

        {loading && (
          <p className="mt-10 text-muted-foreground">Loading lessons…</p>
        )}

        {!loading && categories.length === 0 && (
          <div className="mt-10">
            <p className="text-muted-foreground">
              No lessons are installed. The catalog lives in data/lessons.json.
            </p>
            <Button variant="outline" className="mt-4" onClick={onHome}>
              Back to the menu
            </Button>
          </div>
        )}

        {categories.map((category) => (
          <section key={category.name} className="mt-10">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              {category.name}
            </h2>
            <div className="mt-4 grid gap-5 md:grid-cols-2">
              {category.lessons.map((lesson) => (
                <LessonCard
                  key={lesson.id}
                  lesson={lesson}
                  record={progress[lesson.id]}
                  onOpen={() => void select(lesson.id)}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
