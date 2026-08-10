import { useEffect, useRef, useState } from "react"
import { ArrowLeft, ShieldCheck } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  adminLogin,
  listUsers,
  login,
  whenBridgeReady,
  type UserDto,
} from "@/lib/bridge"
import { CollaborationMark, LttsLogo } from "./Brand"
import { LanyardRack } from "./LanyardRack"

/** The trainer's way in. Deliberately plain and out of the way: operators pick
 * a badge, and the one person who sets up the training types a password. */
function AdminForm({
  onSignedIn,
  onCancel,
}: {
  onSignedIn: () => void
  onCancel: () => void
}) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    const result = await adminLogin(username, password)
    if (result.ok) onSignedIn()
    else setError(result.error ?? "could not sign in")
  }

  return (
    <div className="flex h-full flex-col items-center justify-center px-4">
      <Button variant="ghost" className="absolute left-4 top-4 gap-2" onClick={onCancel}>
        <ArrowLeft className="size-4" />
        Back
      </Button>

      <LttsLogo className="mb-2 h-14 w-auto shrink-0" />
      <p className="mb-6 text-center text-lg text-muted-foreground">
        Sign in to manage operators and lessons.
      </p>

      <form
        className="w-full max-w-sm space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <Input
          autoFocus
          value={username}
          placeholder="Username"
          autoComplete="username"
          className="h-12 text-lg"
          onChange={(e) => {
            setUsername(e.target.value)
            setError(null)
          }}
        />
        <Input
          type="password"
          value={password}
          placeholder="Password"
          autoComplete="current-password"
          className="h-12 text-lg"
          onChange={(e) => {
            setPassword(e.target.value)
            setError(null)
          }}
        />
        <Button type="submit" className="h-12 w-full text-lg">
          Sign in
        </Button>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </form>

      <CollaborationMark className="mt-10" />
    </div>
  )
}

export function LoginScreen({
  onSignedIn,
  onAdmin,
}: {
  onSignedIn: (u: UserDto) => void
  onAdmin: () => void
}) {
  const [name, setName] = useState("")
  const [users, setUsers] = useState<UserDto[]>([])
  const [error, setError] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
  const [asAdmin, setAsAdmin] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  useEffect(() => {
    // The bridge is injected after mount; asking for the roster before it
    // arrives silently returns nothing and the rack shows no badges.
    void whenBridgeReady().then(() => listUsers().then(setUsers))
  }, [])

  async function signIn(value: string) {
    const result = await login(value)
    if (result.ok && result.user) {
      onSignedIn(result.user)
    } else {
      setError(result.error ?? "could not sign in")
    }
  }

  function takeBlankBadge() {
    setTyping(true)
    // The blank badge is a prompt to type, so put the caret where it asks.
    requestAnimationFrame(() => input.current?.focus())
  }

  function backToRack() {
    setTyping(false)
    setName("")
    setError(null)
  }

  if (asAdmin) {
    return (
      <div className="relative h-full">
        <AdminForm onSignedIn={onAdmin} onCancel={() => setAsAdmin(false)} />
      </div>
    )
  }

  return (
    <div className="relative flex h-full flex-col items-center justify-center px-4">
      {typing && (
        <Button
          variant="ghost"
          className="absolute left-4 top-4 gap-2"
          onClick={backToRack}
        >
          <ArrowLeft className="size-4" />
          Back
        </Button>
      )}

      <Button
        variant="ghost"
        className="absolute right-4 top-4 gap-2 text-muted-foreground"
        onClick={() => setAsAdmin(true)}
      >
        <ShieldCheck className="size-4" />
        Admin
      </Button>

      <LttsLogo className="mb-2 h-14 w-auto shrink-0" />
      <p className="mb-1 text-center text-lg text-muted-foreground">
        {typing ? "Type your name to get a badge." : "Take your badge to begin."}
      </p>

      <LanyardRack
        users={users}
        onPickUser={(u) => void signIn(u.name)}
        onPickNew={takeBlankBadge}
      />

      {typing && (
        <form
          className="mt-1 flex w-full max-w-md gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            if (name.trim()) void signIn(name.trim())
          }}
        >
          <Input
            ref={input}
            value={name}
            placeholder="Your name"
            className="h-12 text-lg"
            onChange={(e) => {
              setName(e.target.value)
              setError(null)
            }}
          />
          <Button type="submit" className="h-12 px-8 text-lg">
            Start
          </Button>
        </form>
      )}

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      <CollaborationMark className="mt-3" />
    </div>
  )
}
