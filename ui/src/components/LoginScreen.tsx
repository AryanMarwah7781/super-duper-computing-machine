import { useEffect, useState } from "react"
import { UserRound } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listUsers, login, type UserDto } from "@/lib/bridge"
import { CollaborationMark, LttsLogo } from "./Brand"

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("")
}

export function LoginScreen({ onSignedIn }: { onSignedIn: (u: UserDto) => void }) {
  const [name, setName] = useState("")
  const [users, setUsers] = useState<UserDto[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listUsers().then(setUsers)
  }, [])

  async function signIn(value: string) {
    const result = await login(value)
    if (result.ok && result.user) {
      onSignedIn(result.user)
    } else {
      setError(result.error ?? "could not sign in")
    }
  }

  return (
    <div className="flex h-full flex-col items-center justify-center px-6">
      <div className="w-full max-w-xl">
        <LttsLogo className="mx-auto mb-10 h-20 w-auto" />
        <h1 className="text-center text-4xl font-semibold tracking-tight">
          Welcome
        </h1>
        <p className="mt-3 text-center text-lg text-muted-foreground">
          Tell me your name so I can pick up where you left off.
        </p>

        <form
          className="mt-10 flex gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim()) void signIn(name.trim())
          }}
        >
          <Input
            autoFocus
            value={name}
            placeholder="Your name"
            className="h-14 text-lg"
            onChange={(e) => {
              setName(e.target.value)
              setError(null)
            }}
          />
          <Button type="submit" className="h-14 px-10 text-lg">
            Start
          </Button>
        </form>

        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

        {users.length > 0 && (
          <>
            <p className="mt-12 text-sm font-medium text-muted-foreground">
              Or continue as
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-3">
              {users.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => void signIn(user.name)}
                  className="flex items-center gap-3 rounded-xl border bg-card p-4
                             text-left transition hover:border-primary/50
                             hover:bg-accent focus-visible:outline-none
                             focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <span
                    className="flex size-11 shrink-0 items-center justify-center
                               rounded-full bg-primary/10 text-sm font-semibold
                               text-primary"
                  >
                    {initials(user.name) || <UserRound className="size-5" />}
                  </span>
                  <span className="min-w-0">
                    <span className="block truncate font-medium">
                      {user.name}
                    </span>
                    <span className="block text-xs text-muted-foreground">
                      {user.turns ?? 0}{" "}
                      {user.turns === 1 ? "question" : "questions"}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </>
        )}

        <CollaborationMark className="mt-14" />
      </div>
    </div>
  )
}
