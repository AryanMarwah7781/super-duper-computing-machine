import { Suspense, lazy, useMemo } from "react"
import { makeBadge, makeBlankBadge } from "@/lib/badge"
import type { UserDto } from "@/lib/bridge"

// three + rapier + drei is ~2 MB. Loading it lazily keeps it out of the main
// chunk, so the window paints before the physics stack arrives.
const Lanyard = lazy(() => import("./Lanyard"))

/** A hanging badge that swings; drag it, or click to sign in. */
function Hanging({
  badge,
  label,
  onPick,
}: {
  badge: string
  label: string
  onPick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onPick}
      aria-label={label}
      className="group relative h-[440px] w-[230px] shrink-0 rounded-xl
                 focus-visible:outline-none focus-visible:ring-2
                 focus-visible:ring-ring"
    >
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center">
            <div className="h-56 w-36 animate-pulse rounded-lg bg-muted" />
          </div>
        }
      >
        <Lanyard
          position={[0, 0, 15]}
          gravity={[0, -40, 0]}
          fov={22}
          transparent
          frontImage={badge}
          imageFit="cover"
          // A short strap: at the stock length of 1 the badge hangs past the
          // bottom of its box and gets clipped by the form below.
          segmentLength={0.4}
        />
      </Suspense>
      <span
        className="pointer-events-none absolute inset-x-0 bottom-1 text-center
                   text-sm font-medium text-muted-foreground opacity-0
                   transition group-hover:opacity-100"
      >
        {label}
      </span>
    </button>
  )
}

export function LanyardRack({
  users,
  onPickUser,
  onPickNew,
}: {
  users: UserDto[]
  onPickUser: (user: UserDto) => void
  onPickNew: () => void
}) {
  // Badges are canvas-drawn once per roster change, not per frame.
  const badges = useMemo(
    () => users.map((u) => ({ user: u, image: makeBadge(u.name) })),
    [users],
  )
  const blank = useMemo(() => makeBlankBadge(), [])

  return (
    <div className="flex w-full items-start justify-center gap-2 overflow-x-auto px-4">
      {badges.map(({ user, image }) => (
        <Hanging
          key={user.id}
          badge={image}
          label={`Sign in as ${user.name}`}
          onPick={() => onPickUser(user)}
        />
      ))}
      {/* The spare hook: an unissued badge for whoever is new. */}
      <Hanging badge={blank} label="New operator" onPick={onPickNew} />
    </div>
  )
}
