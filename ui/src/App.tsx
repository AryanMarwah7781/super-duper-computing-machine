import { useCallback, useEffect, useState } from "react"
import { ChatScreen } from "@/components/ChatScreen"
import { HomeScreen } from "@/components/HomeScreen"
import { LoginScreen } from "@/components/LoginScreen"
import { NavBar } from "@/components/NavBar"
import { PlaceholderScreen } from "@/components/PlaceholderScreen"
import { StatusStrip } from "@/components/StatusStrip"
import { LessonPlanArt, SimulatorArt } from "@/components/art/TileArt"
import { useAssist } from "@/hooks/useAssist"
import { useNavigation, type ScreenName } from "@/hooks/useNavigation"
import { history, type HistoryEntry, type UserDto } from "@/lib/bridge"

const TITLES: Record<ScreenName, string> = {
  login: "",
  home: "Menu",
  chat: "Talk to Chatbot",
  lesson: "Lesson Plan",
  simulator: "Start the Simulator",
}

export default function App() {
  const { state, detail, turn, error, busy, ask, showTurn } = useAssist()
  const nav = useNavigation("login")
  const [user, setUser] = useState<UserDto | null>(null)
  const [entries, setEntries] = useState<HistoryEntry[]>([])

  const refreshHistory = useCallback(async (userId: string) => {
    setEntries(await history(userId))
  }, [])

  useEffect(() => {
    if (user) void refreshHistory(user.id)
  }, [user, refreshHistory, turn])

  function signIn(next: UserDto) {
    setUser(next)
    nav.go("home")
  }

  function signOut() {
    setUser(null)
    setEntries([])
    showTurn(null)
    nav.reset("login")
  }

  const onAsk = useCallback(
    (query: string) => {
      void ask(query, user?.id ?? "")
    },
    [ask, user],
  )

  const unavailable = state === "offline" || state === "warming"

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {nav.screen !== "login" && (
        <NavBar
          user={user}
          title={TITLES[nav.screen]}
          canGoBack={nav.canGoBack}
          canGoForward={nav.canGoForward}
          onBack={nav.back}
          onForward={nav.forward}
          onSignOut={signOut}
        />
      )}

      <div className="min-h-0 flex-1">
        {nav.screen === "login" && <LoginScreen onSignedIn={signIn} />}

        {nav.screen === "home" && user && (
          <HomeScreen userName={user.name} onPick={nav.go} />
        )}

        {nav.screen === "chat" && (
          <ChatScreen
            turn={turn}
            entries={entries}
            busy={busy}
            unavailable={unavailable}
            detail={detail}
            error={error}
            state={state}
            onAsk={onAsk}
            onReopen={(entry) => showTurn(entry.turn)}
          />
        )}

        {nav.screen === "lesson" && (
          <PlaceholderScreen
            title="Lesson Plan"
            blurb="A guided sequence that walks through the machine one topic at a time."
            Art={LessonPlanArt}
            onHome={nav.back}
          />
        )}

        {nav.screen === "simulator" && (
          <PlaceholderScreen
            title="Start the Simulator"
            blurb="Step-by-step instructions for bringing the simulator up and running a session."
            Art={SimulatorArt}
            onHome={nav.back}
          />
        )}
      </div>

      {nav.screen !== "login" && (
        <StatusStrip
          state={state}
          detail={detail}
          totalMs={turn?.timing?.total_ms}
        />
      )}
    </div>
  )
}
