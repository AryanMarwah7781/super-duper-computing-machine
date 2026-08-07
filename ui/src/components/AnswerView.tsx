import { CheckCircle2, TriangleAlert } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { TurnDto } from "@/lib/bridge"
import { parseDisplayText } from "@/lib/render"
import { Photo } from "./PhotoStrip"
import { SafetyBanner } from "./SafetyBanner"
import { Step } from "./StepList"

export function AnswerView({
  turn,
  onAsk,
}: {
  turn: TurnDto | null
  onAsk?: (query: string) => void
}) {
  if (!turn) return <div />

  // A command acted on the machine. It is not a manual answer and must not
  // look like one: the operator needs to know at a glance whether something
  // physically happened.
  if (turn.plan.kind === "command" && turn.answer) {
    const worked = !turn.plan.reason.includes("FAILED")
    return (
      <div className="mx-auto max-w-3xl px-6 py-6">
        <div
          className={`flex items-center gap-3 rounded-xl border-l-4 px-5 py-4 ${
            worked
              ? "border-l-green-600 bg-green-50 dark:bg-green-950/40"
              : "border-l-destructive bg-red-50 dark:bg-red-950/40"
          }`}
        >
          {worked ? (
            <CheckCircle2 className="size-6 shrink-0 text-green-600" />
          ) : (
            <TriangleAlert className="size-6 shrink-0 text-destructive" />
          )}
          <span className="text-lg font-medium">
            {turn.answer.display_text}
          </span>
        </div>
      </div>
    )
  }

  // Chris talking, not the manual. No safety banner, no steps, no page
  // number -- none of that exists here, and a citation under something Chris
  // said would imply the manual backed it.
  if (turn.plan.kind === "chat" && turn.answer) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-6">
        <p className="text-lg leading-relaxed">{turn.answer.display_text}</p>
      </div>
    )
  }

  // Nothing matched. Say so plainly — confidently wrong is worse than silent,
  // especially for someone standing next to a machine.
  if (turn.plan.kind === "oos" || !turn.answer) {
    const suggestion = turn.suggestion?.trim()
    return (
      <div className="py-16 text-center">
        <p className="text-2xl font-medium">I don't know.</p>
        <p className="mt-2 text-muted-foreground">
          Nothing in the manual matched that question.
        </p>
        {/* A word was probably misheard. Offer the repair rather than making
            the operator work out which one and say it again. */}
        {suggestion && onAsk && (
          <div className="mt-8">
            <p className="text-sm text-muted-foreground">Did you mean</p>
            <Button
              variant="outline"
              className="mt-2 h-auto max-w-xl whitespace-normal px-5 py-3 text-base"
              onClick={() => onAsk(suggestion)}
            >
              “{suggestion}”
            </Button>
          </div>
        )}
      </div>
    )
  }

  const nodes = parseDisplayText(turn.answer.display_text, turn.answer.images)

  return (
    <article className="mx-auto max-w-3xl px-6 py-6">
      {turn.plan.kind === "synthesize" && (
        <Badge variant="secondary" className="mb-4">
          Excerpt from the manual, not a composed answer
        </Badge>
      )}
      {nodes.map((node, i) => {
        switch (node.kind) {
          case "safety":
            return <SafetyBanner key={i} level={node.level} text={node.text} />
          case "step":
            return <Step key={i} num={node.num} text={node.text} />
          case "photo":
            return <Photo key={i} caption={node.caption} image={node.image} />
          case "heading":
            return (
              <h2 key={i} className="mb-3 mt-2 text-2xl font-semibold">
                {node.text}
              </h2>
            )
          case "row":
            return (
              <div
                key={i}
                className="grid grid-cols-3 gap-4 border-b py-2 text-lg"
              >
                {node.cells.map((c, j) => (
                  <span key={j}>{c}</span>
                ))}
              </div>
            )
          case "citation":
            return (
              <p key={i} className="mt-8 text-sm text-muted-foreground">
                Manual page {node.page}
              </p>
            )
          default:
            return (
              <p key={i} className="py-2 text-lg leading-relaxed">
                {node.text}
              </p>
            )
        }
      })}
    </article>
  )
}
