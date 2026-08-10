import { useEffect, useState } from "react"
import { ArrowRight, MonitorPlay } from "lucide-react"
import { Button } from "@/components/ui/button"
import { starterVideo, type StarterVideo } from "@/lib/bridge"

const STEPS = [
  {
    title: "Start the Connections App",
    body: "Run “Online - Display and CommandARM Simulator.exe” from its own folder. It has to start from there — the hardware and CAN-bus settings are resolved relative to it, and started from anywhere else the console lights never come on.",
  },
  {
    title: "Wait for the console to light up",
    body: "The CommandARM panel comes alive once the app has connected. Until it does, nothing you press leaves the armrest.",
  },
  {
    title: "Start Farming Simulator",
    body: "The FS25 Mods Store client launches the game. This app does not — it watches the machine, it does not drive it.",
  },
  {
    title: "Come back and pick a lesson",
    body: "With the Connections App running, lesson steps tick themselves off as you work the console.",
  },
]

/**
 * How to bring the simulator up, with the recording that shows it.
 *
 * A new operator lands here before anything else — the tiles on the menu all
 * assume a machine that is already running, and the first time somebody sits
 * down that is not true.
 */
export function SimulatorScreen({
  firstRun = false,
  userName = "",
  onDone,
}: {
  firstRun?: boolean
  userName?: string
  onDone: () => void
}) {
  const [video, setVideo] = useState<StarterVideo | null>(null)

  useEffect(() => {
    void starterVideo().then(setVideo)
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-8 py-10">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {firstRun ? "First time here" : "Getting started"}
        </p>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">
          {firstRun && userName
            ? `Welcome, ${userName.split(" ")[0]} — start the simulator first`
            : "Start the simulator"}
        </h1>
        <p className="mt-2 max-w-2xl text-lg text-muted-foreground">
          Watch this once. Everything else in the app — the lessons, the
          console lights, the spoken commands — assumes the simulator is up.
        </p>

        <div className="mt-8 grid gap-8 lg:grid-cols-[1.4fr_1fr]">
          <div>
            {video?.available ? (
              <video
                controls
                playsInline
                preload="metadata"
                className="w-full rounded-2xl bg-black ring-1 ring-foreground/10"
                src={video.url}
              />
            ) : (
              <div className="flex aspect-video w-full flex-col items-center justify-center gap-3 rounded-2xl border border-dashed bg-muted/40 px-8 text-center">
                <MonitorPlay className="size-10 text-muted-foreground" />
                <p className="font-medium">The walkthrough recording is missing.</p>
                {/* Naming the path is the only useful thing this screen can
                    say — somebody has to go and put the file back. */}
                <p className="max-w-md break-all text-sm text-muted-foreground">
                  {video?.path
                    ? `Expected it at ${video.path}. Set ASSIST_STARTER_VIDEO to point somewhere else.`
                    : "Loading…"}
                </p>
              </div>
            )}
          </div>

          <ol className="space-y-5">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-4">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
                  {i + 1}
                </div>
                <div>
                  <h2 className="font-semibold">{step.title}</h2>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                    {step.body}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <div className="mt-10 flex items-center gap-4 border-t pt-6">
          <Button className="gap-2" onClick={onDone}>
            {firstRun ? "I'm ready — take me in" : "Back to the menu"}
            <ArrowRight className="size-4" />
          </Button>
          {firstRun && (
            <p className="text-sm text-muted-foreground">
              You can come back to this any time from the menu.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
