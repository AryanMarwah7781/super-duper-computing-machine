import type { ScreenName } from "@/hooks/useNavigation"
import { ChatbotArt, LessonPlanArt, SimulatorArt } from "./art/TileArt"

type Tile = {
  screen: ScreenName
  title: string
  blurb: string
  Art: (p: { className?: string }) => React.ReactElement
}

const TILES: Tile[] = [
  {
    screen: "lesson",
    title: "Lesson Plan",
    blurb: "Work through a guided sequence, step by step.",
    Art: LessonPlanArt,
  },
  {
    screen: "chat",
    title: "Talk to Chatbot",
    blurb: "Ask anything about the machine and its manual.",
    Art: ChatbotArt,
  },
  {
    screen: "simulator",
    title: "Start the Simulator",
    blurb: "Learn how to bring the simulator up and run it.",
    Art: SimulatorArt,
  },
]

export function HomeScreen({
  userName,
  onPick,
}: {
  userName: string
  onPick: (screen: ScreenName) => void
}) {
  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col justify-center px-8 py-10">
      <div>
        <h1 className="text-4xl font-semibold tracking-tight">
          Hello, {userName.split(" ")[0]}
        </h1>
        <p className="mt-2 text-lg text-muted-foreground">
          What would you like to do?
        </p>
      </div>

      <div className="mt-10 grid gap-6 md:grid-cols-3">
        {TILES.map(({ screen, title, blurb, Art }) => (
          <button
            key={screen}
            type="button"
            onClick={() => onPick(screen)}
            className="group flex flex-col overflow-hidden rounded-2xl border
                       bg-card text-left transition
                       hover:-translate-y-1 hover:border-primary/40
                       hover:shadow-lg focus-visible:outline-none
                       focus-visible:ring-2 focus-visible:ring-ring"
          >
            <div className="flex items-center justify-center bg-muted/40 p-4">
              <Art className="h-44 w-full text-primary transition group-hover:scale-105" />
            </div>
            <div className="p-6">
              <h2 className="text-2xl font-semibold">{title}</h2>
              <p className="mt-2 text-muted-foreground">{blurb}</p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
