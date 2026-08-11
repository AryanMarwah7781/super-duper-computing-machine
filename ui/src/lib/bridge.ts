/**
 * The UI's entire connection to the outside world.
 *
 * There is no fetch in this application. Python owns the network, so every call
 * goes through window.pywebview.api, and Python pushes state changes back
 * through window.assist.emit.
 */

export type ConnectionState = "connecting" | "ready" | "warming" | "offline"

export type ImageDto = {
  id_code: string
  image_path: string
  caption: string
  step_num: number | null
}

export type TurnDto = {
  plan: { kind: string; chunk_ids: number[]; reason: string }
  answer: {
    display_text: string
    spoken_segments: string[]
    safety: { level: string; text: string; page: number | null }[]
    citations: { page: number; procedure_name: string; method: string }[]
    images: ImageDto[]
    render_version: string
    source_hash: string
  } | null
  candidates: {
    chunk_id: number
    score: number
    content_type: string
    procedure_name: string
    page: number | null
  }[]
  /** A repaired query, when a word looks misheard. Empty when nothing matched
   * badly enough to guess at. */
  suggestion?: string
  /** Served from this machine's cache: the same answer the board gave to this
   * question before, without asking it again. */
  recalled?: boolean
  timing: Record<string, number>
}

export type AskResult = {
  ok: boolean
  turn: TurnDto | null
  error: string | null
  stale?: boolean
}

export type UserDto = {
  id: string
  name: string
  created_at: string
  last_seen: string
  turns?: number
  /** False until they have been shown how to bring the simulator up. */
  onboarded?: boolean
}

export type HistoryEntry = {
  ts: string
  query: string
  kind: string
  source: string
  turn: TurnDto | null
}

type Handler = (data: unknown) => void

declare global {
  interface Window {
    pywebview?: {
      api: Record<string, (...a: unknown[]) => Promise<unknown>>
    }
    assist?: { emit: (envelope: { event: string; data: unknown }) => void }
  }
}

const handlers = new Map<string, Set<Handler>>()

export function installEventBus(): void {
  handlers.clear()
  window.assist = {
    emit: ({ event, data }) => {
      handlers.get(event)?.forEach((h) => h(data))
    },
  }
}

export function onEvent(name: string, handler: Handler): () => void {
  if (!handlers.has(name)) handlers.set(name, new Set())
  handlers.get(name)!.add(handler)
  return () => {
    handlers.get(name)?.delete(handler)
  }
}

function bridge() {
  return window.pywebview?.api
}

/**
 * pywebview injects window.pywebview.api *after* the page loads and announces
 * it with a `pywebviewready` event. Anything that calls the bridge on mount —
 * loading the operator roster, for one — races that injection and silently
 * gets nothing back. Await this first.
 *
 * Resolves false in a plain browser (no bridge will ever arrive), so callers
 * degrade instead of hanging.
 */
export function whenBridgeReady(timeoutMs = 5000): Promise<boolean> {
  if (bridge()) return Promise.resolve(true)
  return new Promise((resolve) => {
    let done = false
    const finish = (ok: boolean) => {
      if (done) return
      done = true
      window.removeEventListener("pywebviewready", onReady)
      clearInterval(poll)
      clearTimeout(bail)
      resolve(ok)
    }
    const onReady = () => finish(true)
    window.addEventListener("pywebviewready", onReady)
    // The event fires before some listeners attach in practice, so poll too.
    const poll = setInterval(() => bridge() && finish(true), 100)
    const bail = setTimeout(() => finish(Boolean(bridge())), timeoutMs)
  })
}

export async function ask(
  query: string,
  source = "typed",
  userId = "",
): Promise<AskResult> {
  const api = bridge()
  if (!api) {
    return { ok: false, turn: null, error: "the Python bridge is not available" }
  }
  return (await api.ask(query, source, userId)) as AskResult
}

export async function cancel(): Promise<void> {
  await bridge()?.cancel()
}

export async function listUsers(): Promise<UserDto[]> {
  const api = bridge()
  if (!api) return []
  const result = (await api.list_users()) as { users: UserDto[] }
  return result.users ?? []
}

export async function login(
  name: string,
): Promise<{ ok: boolean; user: UserDto | null; error: string | null }> {
  const api = bridge()
  if (!api) {
    return { ok: false, user: null, error: "the Python bridge is not available" }
  }
  return (await api.login(name)) as {
    ok: boolean
    user: UserDto | null
    error: string | null
    returning?: boolean
  }
}

/**
 * Say something out loud, through the same voice that reads answers.
 *
 * Segments are spoken in order, so a greeting and the question after it are
 * two entries rather than one string — the pause between them is the point.
 * Resolves false when there is no voice (a plain browser, or a rig with no
 * speakers), which callers treat as "carry on silently" rather than an error:
 * the welcome still has to finish if the audio does not.
 */
/**
 * Chris asks a question and opens the microphone for a few seconds.
 *
 * These return as soon as the question has been asked, not when it is
 * answered — the reply arrives as a `choice_heard` / `lesson_heard` event,
 * because the UI has a countdown to run in the meantime.
 *
 * `listening: false` means the microphone was busy or off. Not an error: the
 * screen still works by touch, and asking aloud is an addition to the buttons
 * rather than the only way through.
 */
export async function askChoiceAloud(): Promise<boolean> {
  const r = (await bridge()?.ask_choice()) as { listening?: boolean } | undefined
  return Boolean(r?.listening)
}

export async function askWhichLessonAloud(userId: string): Promise<boolean> {
  const r = (await bridge()?.ask_which_lesson(userId)) as
    | { listening?: boolean }
    | undefined
  return Boolean(r?.listening)
}

/** They tapped instead of answering. */
export async function cancelListening(): Promise<void> {
  await bridge()?.cancel_listening()
}

/**
 * Tell Python what is on screen, so "hey chris" can mean something local.
 *
 * With the lesson list up, "hey chris, lesson two" should open lesson two
 * rather than search the manual for it. Clear it on the way out, or the
 * chatbot inherits a context that is no longer on any screen.
 */
export async function setVoiceContext(
  context: string,
  userId = "",
): Promise<void> {
  await bridge()?.set_voice_context(context, userId)
}

/**
 * Ask for a screen, from whichever panel the operator is standing at.
 *
 * Broadcast rather than handled locally: the chatbot only exists on the
 * chatbot's monitor, so tapping its tile on the lesson monitor has to reach
 * across. Python also brings that panel forward.
 */
export async function navigate(screen: string): Promise<void> {
  await bridge()?.navigate(screen)
}

/**
 * Step aside, or stop.
 *
 * The windows are frameless — no title bar, no X — so these are the only way
 * out. Both panels move together: minimising one of two fullscreen windows
 * leaves the other covering its monitor.
 */
export async function minimizeWindow(): Promise<void> {
  await bridge()?.minimize_window()
}

export async function closeWindow(): Promise<void> {
  await bridge()?.close_window()
}

export async function speak(segments: string[]): Promise<boolean> {
  const api = bridge()
  if (!api) return false
  const result = (await api.speak(segments)) as { ok: boolean }
  return Boolean(result?.ok)
}

export type VoiceStatus = {
  state: "off" | "idle" | "listening" | "transcribing"
  wake_ready: boolean
  stt_ready: boolean
  mic_running: boolean
  error: string | null
}

export async function startVoice(): Promise<VoiceStatus | null> {
  return ((await bridge()?.start_voice()) as VoiceStatus) ?? null
}

export async function stopVoice(): Promise<void> {
  await bridge()?.stop_voice()
}

export type AudioDevice = { index: number; name: string; default: boolean }

export async function audioDevices(): Promise<{
  devices: AudioDevice[]
  current: number | null
}> {
  const api = bridge()
  if (!api) return { devices: [], current: null }
  return (await api.audio_devices()) as { devices: AudioDevice[]; current: number | null }
}

export async function setAudioDevice(index: number | null): Promise<void> {
  await bridge()?.set_audio_device(index)
}

export async function stopSpeaking(): Promise<void> {
  await bridge()?.stop_speaking()
}

export async function setActiveUser(userId: string): Promise<void> {
  await bridge()?.set_active_user(userId)
}

export async function history(userId: string): Promise<HistoryEntry[]> {
  const api = bridge()
  if (!api) return []
  const result = (await api.history(userId)) as { entries: HistoryEntry[] }
  return result.entries ?? []
}

// -- lessons ----------------------------------------------------------------

export type LessonStepDto = {
  header: string
  body: string
  /** Keyboard keys, for the lessons performed in Farming Simulator. */
  keys?: string[]
  icon?: { label?: string; image?: string; glyph?: string }
  /** Present when the machine reports this step; absent when nothing the
   * operator does here reaches the simulator's log. */
  sync?: {
    signals: string[]
    condition: string
    value: string | null
    requires_step: number | null
  }
}

export type LessonDto = {
  id: string
  name: string
  summary: string
  steps: LessonStepDto[]
  /** Its place in the catalog, shown so it can be said back: "lesson two". */
  number?: number
}

export type LessonCategoryDto = { name: string; lessons: LessonDto[] }

export type LessonRecord = { steps_done: number[]; last_opened: string | null }

export type LessonCatalog = {
  categories: LessonCategoryDto[]
  progress: Record<string, LessonRecord>
}

export type OpenLessonResult = {
  ok: boolean
  lesson?: LessonDto
  category?: string
  steps_done?: number[]
  /** True when the simulator's log is being watched: steps complete on their
   * own. False means the operator ticks them off. */
  sync?: boolean
  detail?: string
  error?: string
}

export async function lessons(userId: string): Promise<LessonCatalog> {
  const api = bridge()
  if (!api) return { categories: [], progress: {} }
  return (await api.lessons(userId)) as LessonCatalog
}

export async function openLesson(
  userId: string,
  lessonId: string,
): Promise<OpenLessonResult> {
  const api = bridge()
  if (!api) return { ok: false, error: "the Python bridge is not available" }
  return (await api.open_lesson(userId, lessonId)) as OpenLessonResult
}

export async function closeLesson(): Promise<void> {
  await bridge()?.close_lesson()
}

export async function completeStep(
  userId: string,
  lessonId: string,
  stepIndex: number,
): Promise<number[]> {
  const api = bridge()
  if (!api) return []
  const result = (await api.complete_step(userId, lessonId, stepIndex)) as {
    steps_done: number[]
  }
  return result.steps_done ?? []
}

export async function resetLesson(
  userId: string,
  lessonId: string,
): Promise<void> {
  await bridge()?.reset_lesson(userId, lessonId)
}

// -- getting started --------------------------------------------------------

export type StarterVideo = { url: string; available: boolean; path: string }

export async function starterVideo(): Promise<StarterVideo> {
  const api = bridge()
  if (!api) return { url: "/media/starter.mp4", available: false, path: "" }
  return (await api.starter_video()) as StarterVideo
}

export async function markOnboarded(userId: string): Promise<void> {
  await bridge()?.mark_onboarded(userId)
}

// -- admin ------------------------------------------------------------------

export type AdminLesson = {
  id: string
  name: string
  category: string
  steps: number
  /** True when the CommandARM reports this lesson's steps by itself. */
  live: boolean
}

export type AdminOperator = {
  id: string
  name: string
  created_at: string
  last_seen: string
  onboarded: boolean
  turns: number
  steps_done: number
  steps_total: number
  lessons: Record<
    string,
    { done: number; assigned: boolean; last_opened: string | null }
  >
}

export type AdminOverview = {
  ok: boolean
  lessons: AdminLesson[]
  operators: AdminOperator[]
  refreshed_at: string
  error?: string
}

export async function adminLogin(
  username: string,
  password: string,
): Promise<{ ok: boolean; error: string | null }> {
  const api = bridge()
  if (!api) return { ok: false, error: "the Python bridge is not available" }
  return (await api.admin_login(username, password)) as {
    ok: boolean
    error: string | null
  }
}

export async function adminLogout(): Promise<void> {
  await bridge()?.admin_logout()
}

export async function adminOverview(): Promise<AdminOverview> {
  const api = bridge()
  const empty = { ok: false, lessons: [], operators: [], refreshed_at: "" }
  if (!api) return empty
  return ((await api.admin_overview()) as AdminOverview) ?? empty
}

export async function adminCreateUser(
  name: string,
): Promise<{ ok: boolean; user: UserDto | null; error: string | null }> {
  const api = bridge()
  if (!api) return { ok: false, user: null, error: "no bridge" }
  return (await api.admin_create_user(name)) as {
    ok: boolean
    user: UserDto | null
    error: string | null
  }
}

export async function adminDeleteUser(
  userId: string,
): Promise<{ ok: boolean; error: string | null }> {
  const api = bridge()
  if (!api) return { ok: false, error: "no bridge" }
  return (await api.admin_delete_user(userId)) as {
    ok: boolean
    error: string | null
  }
}

export async function adminSetAssignments(
  userId: string,
  lessonIds: string[],
): Promise<void> {
  await bridge()?.admin_set_assignments(userId, lessonIds)
}
