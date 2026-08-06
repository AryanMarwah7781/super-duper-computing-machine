import { useEffect, useRef, useState } from "react"
import { ArrowLeft } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { listUsers, login, whenBridgeReady, type UserDto } from "@/lib/bridge"
import { CollaborationMark, LttsLogo } from "./Brand"
import { LanyardRack } from "./LanyardRack"

export function LoginScreen({ onSignedIn }: { onSignedIn: (u: UserDto) => void }) {
  const [name, setName] = useState("")
  const [users, setUsers] = useState<UserDto[]>([])
  const [error, setError] = useState<string | null>(null)
  const [typing, setTyping] = useState(false)
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
