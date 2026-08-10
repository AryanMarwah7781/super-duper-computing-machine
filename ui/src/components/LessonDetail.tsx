import { useEffect, useRef } from "react"
import { ArrowLeft, Check, RotateCcw } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { OpenLesson } from "@/hooks/useLessons"
import type { LessonStepDto } from "@/lib/bridge"
import { cn } from "@/lib/utils"

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={done}
      aria-valuemin={0}
      aria-valuemax={total}
    >
      <div
        className="h-full rounded-full bg-primary transition-[width] duration-500"
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

/** A console button, as it is printed on the armrest. Photographs of the real
 * plates where we have them, the panel's own glyph where we don't. */
function ConsolePlate({ icon }: { icon: NonNullable<LessonStepDto["icon"]> }) {
  return (
    <div className="flex w-24 shrink-0 flex-col items-center gap-1.5">
      {icon.image ? (
        <img
          src={`/${icon.image}`}
          alt=""
          className="size-14 rounded-md object-cover ring-1 ring-foreground/15"
        />
      ) : (
        <div className="flex size-14 items-center justify-center rounded-md bg-muted text-2xl ring-1 ring-foreground/15">
          {icon.glyph}
        </div>
      )}
      {icon.label && (
        <span className="text-center text-[11px] font-semibold uppercase leading-tight tracking-wide text-muted-foreground">
          {icon.label}
        </span>
      )}
    </div>
  )
}

function KeyCap({ children }: { children: string }) {
  return (
    <kbd className="rounded-md border border-b-2 bg-muted px-2.5 py-1 font-mono text-sm font-medium">
      {children}
    </kbd>
  )
}

function StepRow({
  index,
  step,
  complete,
  awaiting,
  onTick,
  ref,
}: {
  index: number
  step: LessonStepDto
  complete: boolean
  /** The next thing to do, and the machine is watching for it. */
  awaiting: boolean
  onTick: () => void
  ref?: React.Ref<HTMLLIElement>
}) {
  return (
    <li
      ref={ref}
      data-complete={complete}
      className={cn(
        "flex gap-5 rounded-2xl border bg-card p-5 transition",
        complete && "border-primary/40 bg-primary/5",
        awaiting && "border-primary/40 shadow-sm",
      )}
    >
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-full text-lg font-semibold",
          complete
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-muted-foreground",
        )}
      >
        {complete ? <Check className="size-5" /> : index}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-xl font-semibold">{step.header}</h3>
          {complete ? (
            <Badge variant="secondary">Done</Badge>
          ) : awaiting ? (
            <Badge variant="secondary" className="gap-1.5">
              <span className="size-1.5 animate-pulse rounded-full bg-primary" />
              Watching the console
            </Badge>
          ) : null}
        </div>

        <p className="mt-2 text-lg leading-relaxed text-muted-foreground">
          {step.body}
        </p>

        {step.keys && step.keys.length > 0 && (
          <div className="mt-3 flex items-center gap-2">
            {step.keys.map((key) => (
              <KeyCap key={key}>{key}</KeyCap>
            ))}
          </div>
        )}

        {!complete && (
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <Button variant="outline" size="sm" onClick={onTick}>
              Mark done
            </Button>
            {/* The signal is named because a step that will not tick over is
                the one question this screen has to be able to answer. */}
            {step.sync && (
              <span className="font-mono text-xs text-muted-foreground">
                {step.sync.signals.join(" / ")}
              </span>
            )}
          </div>
        )}
      </div>

      {step.icon && <ConsolePlate icon={step.icon} />}
    </li>
  )
}

export function LessonDetail({
  open,
  done,
  onBack,
  onTick,
  onRestart,
}: {
  open: OpenLesson
  done: number[]
  onBack: () => void
  onTick: (stepIndex: number) => void
  onRestart: () => void
}) {
  const { lesson, category, sync, detail } = open
  const steps = lesson.steps
  const total = steps.length
  const next = steps.findIndex((_, i) => !done.includes(i + 1)) + 1
  const current = useRef<HTMLLIElement>(null)

  // The operator is looking at the armrest, not the screen. When they look
  // back, the step they are on should be the one in front of them.
  useEffect(() => {
    current.current?.scrollIntoView?.({ behavior: "smooth", block: "center" })
  }, [next])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-8 py-8">
        <Button variant="ghost" className="-ml-3 gap-2" onClick={onBack}>
          <ArrowLeft className="size-4" />
          All lessons
        </Button>

        <p className="mt-6 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {category}
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          {lesson.name}
        </h1>

        {detail && (
          <div
            className={cn(
              "mt-4 flex items-start gap-3 rounded-xl border-l-4 px-4 py-3",
              sync
                ? "border-l-primary bg-primary/5"
                : "border-l-muted-foreground/40 bg-muted/50",
            )}
          >
            <span
              className={cn(
                "mt-1.5 size-2 shrink-0 rounded-full",
                sync ? "animate-pulse bg-primary" : "bg-muted-foreground/50",
              )}
            />
            <p className="text-sm leading-relaxed">{detail}</p>
          </div>
        )}

        <div className="mt-8 flex items-end justify-between gap-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Procedure
          </h2>
          <span className="text-sm text-muted-foreground">
            {done.length} of {total} complete
          </span>
        </div>
        <div className="mt-2">
          <ProgressBar done={done.length} total={total} />
        </div>

        <ul className="mt-6 space-y-4">
          {steps.map((step, i) => {
            const index = i + 1
            return (
              <StepRow
                key={index}
                ref={index === next ? current : undefined}
                index={index}
                step={step}
                complete={done.includes(index)}
                awaiting={sync && index === next && Boolean(step.sync)}
                onTick={() => onTick(index)}
              />
            )
          })}
        </ul>

        <div className="mt-8 flex items-center justify-between gap-4 border-t pt-6">
          <Button variant="ghost" className="gap-2" onClick={onRestart}>
            <RotateCcw className="size-4" />
            Start over
          </Button>
          {done.length >= total && total > 0 && (
            <p className="text-sm font-medium text-primary">
              Lesson complete — all {total} steps.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
