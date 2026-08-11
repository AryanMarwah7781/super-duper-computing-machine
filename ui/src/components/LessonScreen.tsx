import { useEffect, useRef } from "react"
import { ChevronRight } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useLessons } from "@/hooks/useLessons"
import { useListening } from "@/hooks/useListening"
import {
  askWhichLessonAloud,
  closeLesson,
  onEvent,
  setVoiceContext,
  speak,
  type LessonDto,
  type LessonRecord,
} from "@/lib/bridge"
import { Listening } from "./ChoiceScreen"
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
        {/* The number is on screen because it is sayable: "lesson two" only
            works if the operator can see which one that is. */}
        {lesson.number != null && (
          <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/12 text-sm font-semibold text-primary">
            {lesson.number}
          </span>
        )}
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
  /** Only the panel that owns the voice asks aloud. */
  speaks = false,
}: {
  userId: string
  onHome: () => void
  speaks?: boolean
}) {
  const { categories, progress, open, done, loading, select, close, tick, restart } =
    useLessons(userId)
  const listen = useListening("lesson_heard")
  const asked = useRef(false)

  // Leaving the screen entirely — signing out, or the menu — must stop the
  // log being watched. Nothing here would show a step completing.
  useEffect(() => () => void closeLesson(), [])

  // While the list is up, "hey chris, lesson two" is a lesson rather than a
  // question for the manual. Cleared on the way out and while a lesson is
  // open, or the chatbot inherits a context that is no longer on any screen.
  useEffect(() => {
    void setVoiceContext(open ? "" : "lesson", userId)
    return () => void setVoiceContext("")
  }, [open, userId])

  // "Which lesson?" — asked once the list is actually on screen. Asking while
  // it is still loading would name a numbering the operator cannot see, and
  // "the third one" has to mean the third one they are looking at.
  useEffect(() => {
    if (!speaks || asked.current || loading || open) return
    if (categories.length === 0) return
    asked.current = true

    let cancelled = false
    void (async () => {
      await speak(["Which lesson would you like?",
                   "You can say its name, or its number."])
      // After the question, never during it: the gate is shut while the app
      // talks so it cannot record its own voice.
      if (!cancelled) void askWhichLessonAloud(userId)
    })()
    return () => {
      cancelled = true
    }
  }, [speaks, loading, open, categories.length, userId])

  // Python matched the reply against the list; open what it found. An
  // unrecognised or ambiguous answer comes back null and is left alone — the
  // list is still on screen and can be tapped.
  useEffect(() => {
    return onEvent("lesson_heard", (data) => {
      const id = (data as { lesson_id?: string | null })?.lesson_id
      if (id) void select(id)
    })
  }, [select])

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
        <div className="flex items-start justify-between gap-8">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">
              Pick a lesson
            </h1>
            <p className="mt-2 text-lg text-muted-foreground">
              Each one is a short procedure on the machine. Where the CommandARM
              reports back, steps tick themselves off as you work the console.
            </p>
          </div>
          {listen.listening && (
            <div className="w-64 shrink-0 pt-1">
              <Listening
                remaining={listen.remaining}
                fraction={listen.fraction}
              />
            </div>
          )}
        </div>

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
                  onOpen={() => {
                    // Tapped instead of answering: close the microphone
                    // rather than leaving it open behind a screen that has
                    // already moved on.
                    listen.dismiss()
                    void select(lesson.id)
                  }}
                />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  )
}
