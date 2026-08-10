import { useCallback, useEffect, useState } from "react"
import {
  Check,
  ChevronDown,
  Plus,
  RotateCw,
  Trash2,
  UserPlus,
} from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { ProgressBar } from "@/components/LessonDetail"
import {
  adminCreateUser,
  adminDeleteUser,
  adminOverview,
  adminSetAssignments,
  whenBridgeReady,
  type AdminLesson,
  type AdminOperator,
} from "@/lib/bridge"
import { cn } from "@/lib/utils"

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}

function shortTime(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  const days = Math.round(
    (new Date().setHours(0, 0, 0, 0) - new Date(at).setHours(0, 0, 0, 0)) /
      86_400_000,
  )
  const clock = at.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
  if (days === 0) return clock
  if (days === 1) return "yesterday"
  return at.toLocaleDateString([], { day: "numeric", month: "short" })
}

/** The lesson toggle. There is no checkbox in this UI kit, and a lesson being
 * assigned is a state worth reading at a glance rather than a tick to hunt. */
function AssignToggle({
  on,
  onToggle,
  label,
}: {
  on: boolean
  onToggle: () => void
  label: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={onToggle}
      className={cn(
        "flex size-5 shrink-0 items-center justify-center rounded-md border transition",
        on
          ? "border-primary bg-primary text-primary-foreground"
          : "border-input bg-background hover:border-primary/50",
      )}
    >
      {on && <Check className="size-3.5" />}
    </button>
  )
}

function OperatorRow({
  operator,
  lessons,
  onAssign,
  onDelete,
}: {
  operator: AdminOperator
  lessons: AdminLesson[]
  onAssign: (lessonIds: string[]) => void
  onDelete: () => void
}) {
  const [open, setOpen] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const assigned = lessons
    .filter((l) => operator.lessons[l.id]?.assigned !== false)
    .map((l) => l.id)

  function toggle(lessonId: string) {
    const next = assigned.includes(lessonId)
      ? assigned.filter((id) => id !== lessonId)
      : [...assigned, lessonId]
    onAssign(next)
  }

  const categories = [...new Set(lessons.map((l) => l.category))]
  const pct =
    operator.steps_total > 0
      ? Math.round((operator.steps_done / operator.steps_total) * 100)
      : 0

  return (
    <li className="rounded-2xl border bg-card">
      <div className="flex items-center gap-4 p-5">
        <div className="flex size-11 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-semibold text-muted-foreground">
          {initials(operator.name)}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{operator.name}</h3>
            {!operator.onboarded && (
              <Badge variant="secondary">Has not started yet</Badge>
            )}
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Last seen {shortTime(operator.last_seen)} · {operator.turns}{" "}
            {operator.turns === 1 ? "question" : "questions"} ·{" "}
            {assigned.length} of {lessons.length} lessons assigned
          </p>
        </div>

        <div className="w-48 shrink-0">
          <ProgressBar done={operator.steps_done} total={operator.steps_total} />
          <p className="mt-1.5 text-right text-sm text-muted-foreground">
            {operator.steps_done} of {operator.steps_total} steps · {pct}%
          </p>
        </div>

        <Button
          variant="ghost"
          size="sm"
          className="gap-1"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          Lessons
          <ChevronDown
            className={cn("size-4 transition", open && "rotate-180")}
          />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Remove ${operator.name}`}
          onClick={() => setConfirming(true)}
        >
          <Trash2 className="size-4 text-muted-foreground" />
        </Button>
      </div>

      {/* Deleting takes their history and progress with it, so the question is
          asked in place rather than in a dialog that can be dismissed by
          reflex. */}
      {confirming && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t bg-destructive/5 px-5 py-4">
          <p className="text-sm">
            Remove <strong>{operator.name}</strong>? Their questions and every
            lesson step they have completed go with them.
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setConfirming(false)}>
              Keep
            </Button>
            <Button
              size="sm"
              className="bg-destructive text-white hover:bg-destructive/90"
              onClick={() => {
                setConfirming(false)
                onDelete()
              }}
            >
              Remove
            </Button>
          </div>
        </div>
      )}

      {open && (
        <div className="border-t px-5 py-4">
          {categories.map((category) => (
            <div key={category} className="mt-4 first:mt-0">
              <h4 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                {category}
              </h4>
              <ul className="mt-2 space-y-1">
                {lessons
                  .filter((l) => l.category === category)
                  .map((lesson) => {
                    const record = operator.lessons[lesson.id]
                    const done = record?.done ?? 0
                    const isAssigned = record?.assigned !== false
                    return (
                      <li
                        key={lesson.id}
                        className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/50"
                      >
                        <AssignToggle
                          on={isAssigned}
                          label={`${lesson.name} for ${operator.name}`}
                          onToggle={() => toggle(lesson.id)}
                        />
                        <span
                          className={cn(
                            "flex-1 truncate",
                            !isAssigned && "text-muted-foreground line-through",
                          )}
                        >
                          {lesson.name}
                        </span>
                        {lesson.live && (
                          <Badge variant="secondary">CommandARM</Badge>
                        )}
                        <div className="w-28">
                          <ProgressBar done={done} total={lesson.steps} />
                        </div>
                        <span className="w-16 text-right text-sm tabular-nums text-muted-foreground">
                          {done} / {lesson.steps}
                        </span>
                      </li>
                    )
                  })}
              </ul>
            </div>
          ))}
        </div>
      )}
    </li>
  )
}

export function AdminScreen() {
  const [lessons, setLessons] = useState<AdminLesson[]>([])
  const [operators, setOperators] = useState<AdminOperator[]>([])
  const [refreshed, setRefreshed] = useState("")
  const [busy, setBusy] = useState(false)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState("")
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setBusy(true)
    const overview = await adminOverview()
    if (overview.ok) {
      setLessons(overview.lessons)
      setOperators(overview.operators)
      setRefreshed(overview.refreshed_at)
    }
    setBusy(false)
  }, [])

  useEffect(() => {
    void whenBridgeReady().then(refresh)
  }, [refresh])

  async function create() {
    const value = name.trim()
    if (!value) return
    const result = await adminCreateUser(value)
    if (!result.ok) {
      setError(result.error ?? "could not add that operator")
      return
    }
    setName("")
    setAdding(false)
    setError(null)
    await refresh()
  }

  async function assign(userId: string, lessonIds: string[]) {
    // Paint it immediately: the toggle is the whole interaction, and waiting
    // for a round trip before it moves makes the screen feel broken.
    setOperators((prev) =>
      prev.map((o) =>
        o.id === userId
          ? {
              ...o,
              lessons: Object.fromEntries(
                lessons.map((l) => [
                  l.id,
                  {
                    done: o.lessons[l.id]?.done ?? 0,
                    last_opened: o.lessons[l.id]?.last_opened ?? null,
                    assigned: lessonIds.includes(l.id),
                  },
                ]),
              ),
            }
          : o,
      ),
    )
    await adminSetAssignments(userId, lessonIds)
    await refresh()
  }

  async function remove(userId: string) {
    await adminDeleteUser(userId)
    await refresh()
  }

  const totalSteps = operators.reduce((n, o) => n + o.steps_total, 0)
  const doneSteps = operators.reduce((n, o) => n + o.steps_done, 0)

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Operators</h1>
            <p className="mt-2 text-muted-foreground">
              {operators.length}{" "}
              {operators.length === 1 ? "person" : "people"} on the roster ·{" "}
              {doneSteps} of {totalSteps} assigned steps complete
            </p>
          </div>

          <div className="flex items-center gap-2">
            {refreshed && (
              <span className="text-sm text-muted-foreground">
                Updated {shortTime(refreshed)}
              </span>
            )}
            <Button
              variant="outline"
              className="gap-2"
              disabled={busy}
              onClick={() => void refresh()}
            >
              <RotateCw className={cn("size-4", busy && "animate-spin")} />
              Refresh progress
            </Button>
            <Button className="gap-2" onClick={() => setAdding((v) => !v)}>
              <UserPlus className="size-4" />
              Add operator
            </Button>
          </div>
        </div>

        {adding && (
          <form
            className="mt-6 flex flex-wrap items-center gap-3 rounded-2xl border bg-card p-5"
            onSubmit={(e) => {
              e.preventDefault()
              void create()
            }}
          >
            <Input
              autoFocus
              value={name}
              placeholder="Their name"
              className="h-11 max-w-xs text-base"
              onChange={(e) => {
                setName(e.target.value)
                setError(null)
              }}
            />
            <Button type="submit" className="h-11 gap-2">
              <Plus className="size-4" />
              Create
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="h-11"
              onClick={() => {
                setAdding(false)
                setName("")
                setError(null)
              }}
            >
              Cancel
            </Button>
            <p className="w-full text-sm text-muted-foreground">
              They sign in by picking their name — there is no password. Every
              lesson is theirs to begin with; switch off the ones they should
              not work through yet.
            </p>
          </form>
        )}

        {error && <p className="mt-4 text-sm text-destructive">{error}</p>}

        <ul className="mt-8 space-y-4">
          {operators.map((operator) => (
            <OperatorRow
              key={operator.id}
              operator={operator}
              lessons={lessons}
              onAssign={(ids) => void assign(operator.id, ids)}
              onDelete={() => void remove(operator.id)}
            />
          ))}
        </ul>

        {operators.length === 0 && !busy && (
          <p className="mt-10 text-muted-foreground">
            Nobody on the roster yet. Add the first operator above.
          </p>
        )}
      </div>
    </div>
  )
}
