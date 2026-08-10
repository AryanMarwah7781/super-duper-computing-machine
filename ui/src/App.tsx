import { useCallback, useEffect, useState } from "react"
import { AdminScreen } from "@/components/AdminScreen"
import { ChatScreen } from "@/components/ChatScreen"
import { HomeScreen } from "@/components/HomeScreen"
import { LessonScreen } from "@/components/LessonScreen"
import { LoginScreen } from "@/components/LoginScreen"
import { NavBar } from "@/components/NavBar"
import { SimulatorScreen } from "@/components/SimulatorScreen"
import { SplashScreen } from "@/components/SplashScreen"
import { StatusStrip } from "@/components/StatusStrip"
import { VoiceIndicator } from "@/components/VoiceIndicator"
import { VoiceSettings } from "@/components/VoiceSettings"
import { useAssist } from "@/hooks/useAssist"
import { useNavigation, type ScreenName } from "@/hooks/useNavigation"
import {
  adminLogout,
  history,
  markOnboarded,
  setActiveUser,
  startVoice,
  stopVoice,
  type HistoryEntry,
  type UserDto,
} from "@/lib/bridge"

const TITLES: Record<ScreenName, string> = {
  login: "",
  home: "Menu",
  chat: "Talk to Chatbot",
  lesson: "Lesson Plan",
  simulator: "Start the Simulator",
  admin: "Training Admin",
}

export default function App() {
  const {
    state,
    detail,
    messages,
    busy,
    voice,
    level,
    speaking,
    ask,
    appendHistory,
    clearConversation,
  } = useAssist()
  const nav = useNavigation("login")
  const [user, setUser] = useState<UserDto | null>(null)
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [booting, setBooting] = useState(true)
  const [admin, setAdmin] = useState(false)

  const refreshHistory = useCallback(async (userId: string) => {
    setEntries(await history(userId))
  }, [])

  useEffect(() => {
    if (user) void refreshHistory(user.id)
  }, [user, refreshHistory, messages.length])

  function signIn(next: UserDto) {
    setUser(next)
    // Voice listens only for a signed-in operator: answers are recorded
    // against their history, and an idle machine listening to the room is a
    // different product decision.
    void setActiveUser(next.id).then(() => startVoice())
    // Somebody the admin added this morning has never started the simulator.
    // The menu assumes a machine that is already running, so they see how to
    // bring it up before they see anything else.
    nav.go(next.onboarded === false ? "simulator" : "home")
  }

  /** They have watched the walkthrough. Recorded, so it never opens on them
   * again — and the tile stays on the menu for when they want it. */
  function finishOnboarding() {
    if (user && user.onboarded === false) {
      void markOnboarded(user.id)
      setUser({ ...user, onboarded: true })
    }
    nav.go("home")
  }

  function signOut() {
    void stopVoice()
    void setActiveUser("")
    if (admin) void adminLogout()
    setAdmin(false)
    setUser(null)
    setEntries([])
    clearConversation()
    nav.reset("login")
  }

  const onAsk = useCallback(
    (query: string) => {
      void ask(query, user?.id ?? "")
    },
    [ask, user],
  )

  const unavailable = state === "offline" || state === "warming"
  const lastAnswer = [...messages].reverse().find((m) => m.role === "assistant")
  const totalMs =
    lastAnswer && lastAnswer.role === "assistant"
      ? lastAnswer.turn?.timing?.total_ms
      : undefined

  if (booting) {
    return (
      <div className="h-screen bg-background text-foreground">
        <SplashScreen onDone={() => setBooting(false)} />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      {nav.screen !== "login" && (
        <NavBar
          user={user}
          admin={admin}
          title={TITLES[nav.screen]}
          canGoBack={nav.canGoBack}
          canGoForward={nav.canGoForward}
          onBack={nav.back}
          onForward={nav.forward}
          onSignOut={signOut}
        />
      )}

      <div className="min-h-0 flex-1">
        {nav.screen === "login" && (
          <LoginScreen
            onSignedIn={signIn}
            onAdmin={() => {
              setAdmin(true)
              nav.go("admin")
            }}
          />
        )}

        {nav.screen === "admin" && admin && <AdminScreen />}

        {nav.screen === "home" && user && (
          <HomeScreen userName={user.name} onPick={nav.go} />
        )}

        {nav.screen === "chat" && (
          <ChatScreen
            messages={messages}
            entries={entries}
            busy={busy}
            unavailable={unavailable}
            detail={detail}
            state={state}
            onAsk={onAsk}
            onReopen={(entry) => appendHistory(entry.query, entry.turn)}
            voice={voice}
            level={level}
          />
        )}

        {nav.screen === "lesson" && user && (
          <LessonScreen userId={user.id} onHome={nav.back} />
        )}

        {nav.screen === "simulator" && (
          <SimulatorScreen
            firstRun={user?.onboarded === false}
            userName={user?.name ?? ""}
            onDone={finishOnboarding}
          />
        )}
      </div>

      {nav.screen !== "login" && (
        <StatusStrip
          state={state}
          detail={detail}
          totalMs={totalMs}
          voice={
            <>
              <VoiceIndicator state={voice} level={level} />
              <VoiceSettings state={voice} speaking={speaking} />
            </>
          }
        />
      )}
    </div>
  )
}
