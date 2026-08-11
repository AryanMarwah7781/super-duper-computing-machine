import { useCallback, useEffect, useMemo, useState } from "react"
import { AdminScreen } from "@/components/AdminScreen"
import { ChatScreen } from "@/components/ChatScreen"
import { ChoiceScreen, type Choice } from "@/components/ChoiceScreen"
import { HomeScreen } from "@/components/HomeScreen"
import { LessonScreen } from "@/components/LessonScreen"
import { LoginScreen } from "@/components/LoginScreen"
import { NavBar } from "@/components/NavBar"
import { SimulatorScreen } from "@/components/SimulatorScreen"
import { SplashScreen } from "@/components/SplashScreen"
import { StatusStrip } from "@/components/StatusStrip"
import { VoiceIndicator } from "@/components/VoiceIndicator"
import { VoiceSettings } from "@/components/VoiceSettings"
import { WelcomeScreen } from "@/components/WelcomeScreen"
import { WindowControls } from "@/components/WindowControls"
import { useAssist } from "@/hooks/useAssist"
import { useNavigation, type ScreenName } from "@/hooks/useNavigation"
import { isVoiceOwner, readRole, showsChat, showsLesson } from "@/lib/role"
import {
  adminLogout,
  history,
  markOnboarded,
  navigate,
  onEvent,
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

/**
 * The opening runs in three beats before the app proper: Chris arrives and
 * greets whoever signed in, the two choices are offered, then the panel
 * settles into its job. `idle` is the black screen before anybody has.
 */
type Phase = "idle" | "welcome" | "choice" | "app"

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
  const role = useMemo(() => readRole(), [])
  const nav = useNavigation("login")
  const [user, setUser] = useState<UserDto | null>(null)
  const [returning, setReturning] = useState(false)
  const [phase, setPhase] = useState<Phase>("idle")
  const [entries, setEntries] = useState<HistoryEntry[]>([])
  const [booting, setBooting] = useState(true)
  const [admin, setAdmin] = useState(false)

  const refreshHistory = useCallback(async (userId: string) => {
    setEntries(await history(userId))
  }, [])

  useEffect(() => {
    if (user) void refreshHistory(user.id)
  }, [user, refreshHistory, messages.length])

  /** Shared by both ways in: the sign-in screen, and the login file. */
  const begin = useCallback((next: UserDto, isReturning: boolean) => {
    setUser(next)
    setReturning(isReturning)
    setPhase("welcome")
  }, [])

  /** Drop this panel's session without announcing it again.
   *
   * Sign-out is broadcast, and every panel runs this when it hears it. If it
   * announced in turn, the two panels would answer each other's sign-out for
   * as long as the app stayed open.
   */
  const clearSession = useCallback(() => {
    setAdmin(false)
    setUser(null)
    setReturning(false)
    setPhase("idle")
    setEntries([])
    clearConversation()
    nav.reset("login")
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clearConversation])

  // Somebody signed in or out on the other panel, or the external system
  // wrote the login file. Either way this window follows.
  useEffect(() => {
    const offExternal = onEvent("external_login", (data) => {
      const d = data as { user: UserDto; returning: boolean }
      if (d?.user) begin(d.user, Boolean(d.returning))
    })
    const offActive = onEvent("active_user", (data) => {
      const d = data as { user: UserDto | null }
      if (d?.user) {
        setUser((prev) => (prev?.id === d.user!.id ? prev : d.user))
        setPhase((prev) => (prev === "idle" ? "welcome" : prev))
      } else {
        // Signed out. One operator walking away has to clear every monitor —
        // the next person must not find the last one's history still open on
        // the panel nobody happened to be standing at.
        clearSession()
      }
    })
    // A tile tapped on either monitor. The panel that owns that screen shows
    // it; the others stay where they are rather than following along.
    const offNav = onEvent("navigate", (data) => {
      const screen = (data as { screen?: string })?.screen as ScreenName
      if (!screen) return
      if (screen === "chat" && !showsChat(role)) return
      if (screen === "lesson" && !showsLesson(role)) return
      setPhase("app")
      nav.reset(screen)
    })
    return () => {
      offExternal()
      offActive()
      offNav()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [begin, clearSession, role])

  function signIn(next: UserDto) {
    // Voice listens only for a signed-in operator: answers are recorded
    // against their history, and an idle machine listening to the room is a
    // different product decision.
    void setActiveUser(next.id).then(() => startVoice())
    begin(next, next.onboarded !== false)
  }

  /** The welcome has played. Offer the two ways in. */
  function afterWelcome() {
    setPhase("choice")
  }

  function pick(choice: Choice) {
    // Somebody the admin added this morning has never started the simulator.
    // The menu assumes a machine that is already running, so they see how to
    // bring it up before anything else — whichever way they chose. This one
    // is local: the walkthrough belongs on the panel they are looking at.
    if (user?.onboarded === false) {
      setPhase("app")
      nav.reset("simulator")
      return
    }
    // Everything else goes through Python, so the choice lands on the panel
    // that owns it however many monitors away that is.
    void navigate(choice)
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
    if (admin) void adminLogout()
    // Announced, not just done here. setActiveUser("") broadcasts, and every
    // other panel clears itself when it hears it.
    void setActiveUser("")
    clearSession()
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
        <WindowControls />
        <SplashScreen onDone={() => setBooting(false)} />
      </div>
    )
  }

  // Before anybody has signed in, a secondary panel is simply black. The
  // window that owns sign-in shows the sign-in screen; the others must not
  // show a second one, or there are two ways in and they can disagree.
  // The controls go on even here — a black panel with no way out of it is
  // the single worst thing this app could put on a monitor.
  if (phase === "idle" && !showsChat(role)) {
    return (
      <div className="h-screen w-screen bg-black">
        <WindowControls />
      </div>
    )
  }

  if (phase === "welcome" && user) {
    return (
      <div className="h-screen w-screen bg-black">
        <WindowControls />
        <WelcomeScreen
          name={user.name}
          returning={returning}
          speaks={isVoiceOwner(role)}
          onDone={afterWelcome}
        />
      </div>
    )
  }

  if (phase === "choice" && user) {
    return (
      <div className="h-screen w-screen bg-black">
        <WindowControls />
        <ChoiceScreen
          name={user.name}
          returning={returning}
          speaks={isVoiceOwner(role)}
          onPick={pick}
        />
      </div>
    )
  }

  return (
    <div className="flex h-screen flex-col bg-background text-foreground">
      <WindowControls />
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
              setPhase("app")
              nav.go("admin")
            }}
          />
        )}

        {nav.screen === "admin" && admin && <AdminScreen />}

        {nav.screen === "home" && user && (
          <HomeScreen
            userName={user.name}
            // The menu is on whichever panel the operator is at, but its
            // tiles are not: chat and lessons live on monitors of their own.
            onPick={(screen) =>
              screen === "chat" || screen === "lesson"
                ? void navigate(screen)
                : nav.go(screen)
            }
          />
        )}

        {nav.screen === "chat" && showsChat(role) && (
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

        {nav.screen === "lesson" && user && showsLesson(role) && (
          <LessonScreen
            userId={user.id}
            onHome={nav.back}
            // On the two-panel rig the lesson list is not on the panel that
            // owns the voice, so it asks for itself. In the single-window
            // arrangement that is the same panel and this is simply true.
            speaks={isVoiceOwner(role) || showsLesson(role)}
          />
        )}

        {nav.screen === "simulator" && (
          <SimulatorScreen
            firstRun={user?.onboarded === false}
            userName={user?.name ?? ""}
            onDone={finishOnboarding}
          />
        )}

        {/* This panel does not draw the screen the other one is on. Saying so
            beats a blank area that looks like something failed to load. */}
        {((nav.screen === "chat" && !showsChat(role)) ||
          (nav.screen === "lesson" && !showsLesson(role))) && (
          <div className="flex h-full items-center justify-center text-sm uppercase tracking-[0.25em] text-muted-foreground">
            {nav.screen === "chat" ? "chatbot" : "lesson plan"} is on the other
            screen
          </div>
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
