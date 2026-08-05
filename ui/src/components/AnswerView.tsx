import { Badge } from "@/components/ui/badge"
import type { TurnDto } from "@/lib/bridge"
import { parseDisplayText } from "@/lib/render"
import { Photo } from "./PhotoStrip"
import { SafetyBanner } from "./SafetyBanner"
import { Step } from "./StepList"

export function AnswerView({ turn }: { turn: TurnDto | null }) {
  if (!turn) return <div />

  // Nothing matched. Say so plainly — confidently wrong is worse than silent,
  // especially for someone standing next to a machine.
  if (turn.plan.kind === "oos" || !turn.answer) {
    return (
      <div className="py-16 text-center">
        <p className="text-2xl font-medium">I don't know.</p>
        <p className="mt-2 text-muted-foreground">
          Nothing in the manual matched that question.
        </p>
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
