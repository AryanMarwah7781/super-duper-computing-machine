import { ArrowLeft, ArrowRight, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { UserDto } from "@/lib/bridge"

export function NavBar({
  user,
  canGoBack,
  canGoForward,
  onBack,
  onForward,
  onSignOut,
  title,
}: {
  user: UserDto | null
  canGoBack: boolean
  canGoForward: boolean
  onBack: () => void
  onForward: () => void
  onSignOut: () => void
  title: string
}) {
  return (
    <header className="flex items-center gap-2 border-b px-4 py-3">
      <Button
        variant="ghost"
        size="icon"
        className="size-10"
        disabled={!canGoBack}
        aria-label="Back"
        onClick={onBack}
      >
        <ArrowLeft className="size-5" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="size-10"
        disabled={!canGoForward}
        aria-label="Forward"
        onClick={onForward}
      >
        <ArrowRight className="size-5" />
      </Button>

      <span className="ml-2 text-lg font-medium">{title}</span>

      {user && (
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{user.name}</span>
          <Button
            variant="ghost"
            size="icon"
            className="size-10"
            aria-label="Sign out"
            onClick={onSignOut}
          >
            <LogOut className="size-5" />
          </Button>
        </div>
      )}
    </header>
  )
}
