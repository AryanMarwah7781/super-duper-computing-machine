import { ArrowLeft, ArrowRight, LogOut } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { UserDto } from "@/lib/bridge"
import { LttsLogo } from "./Brand"

export function NavBar({
  user,
  admin = false,
  canGoBack,
  canGoForward,
  onBack,
  onForward,
  onSignOut,
  title,
}: {
  user: UserDto | null
  /** Signed in as the trainer rather than as an operator. */
  admin?: boolean
  canGoBack: boolean
  canGoForward: boolean
  onBack: () => void
  onForward: () => void
  onSignOut: () => void
  title: string
}) {
  return (
    // The right-hand end is not free: the window's minimise and close sit
    // there, floating over everything, because the window is frameless and
    // has no title bar to put them in. Reserving the corner keeps Sign out
    // from ending up under the X — they are one misplaced tap apart, and one
    // of them ends the session for every panel.
    <header className="flex items-center gap-2 border-b py-3 pl-4 pr-28">
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

      {/* The brand rides in the chrome, so it is present on every screen
          without competing with the answer. */}
      <LttsLogo className="ml-6 hidden h-9 w-auto opacity-90 sm:block" />

      {(user || admin) && (
        <div className="ml-auto flex items-center gap-3">
          <span className="text-sm text-muted-foreground">
            {user ? user.name : "Admin"}
          </span>
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
