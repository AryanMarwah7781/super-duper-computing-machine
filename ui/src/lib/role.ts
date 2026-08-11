/**
 * Which panel this window is, and therefore what it shows.
 *
 * Python opens one window per role and puts each on its own monitor; all of
 * them load this same bundle with a different `?role=`. One UI, three jobs.
 *
 * `all` is the single-window arrangement — everything in one place. It is what
 * a browser gets, what `--single` gives, and what happens when two roles land
 * on the same monitor, so it has to stay a first-class mode rather than a
 * degraded one.
 */
export type Role = "chat" | "lesson" | "all"

const ROLES: Role[] = ["chat", "lesson", "all"]

export function readRole(search: string = window.location.search): Role {
  const raw = new URLSearchParams(search).get("role")
  // An unknown role shows everything rather than nothing. A typo in a launch
  // argument should cost a misplaced window, not a black screen with no way
  // to tell what went wrong.
  return (ROLES as string[]).includes(raw ?? "") ? (raw as Role) : "all"
}

/** Does this window draw the chatbot? */
export function showsChat(role: Role): boolean {
  return role === "chat" || role === "all"
}

/** Does this window draw the lesson plan? */
export function showsLesson(role: Role): boolean {
  return role === "lesson" || role === "all"
}

/**
 * Only one window may speak, or the greeting arrives twice over.
 *
 * The chat panel is the voice, because that is the one somebody is sitting in
 * front of. In the single-window arrangement that is the same window anyway.
 */
export function isVoiceOwner(role: Role): boolean {
  return role === "chat" || role === "all"
}
