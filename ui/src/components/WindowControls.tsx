import { useState } from "react"
import { closeWindow, minimizeWindow } from "@/lib/bridge"

/**
 * Minimise and close, because the windows have no title bar to put them in.
 *
 * Frameless was chosen so the panels read as one installed thing rather than
 * three browser windows, and the cost of that is there is no X. This is the
 * X. It sits on every screen including the black ones and the welcome, since
 * "the video will not play and I cannot get out" is exactly the moment
 * somebody needs it.
 *
 * Closing asks first. There is one process behind both panels and it also
 * holds the microphone and the connection to the board, so a misplaced click
 * does not end a session in front of a room.
 */
export function WindowControls() {
  const [confirming, setConfirming] = useState(false)

  return (
    <div
      // Hard into the corner. Every pixel of padding here is a pixel closer
      // to whatever the screen underneath puts at its own top right — which
      // on the chatbot and lesson panels is Sign out.
      className="fixed right-0 top-0 z-50 flex items-start gap-1 p-1"
      // The window is not draggable, but a control strip that swallows its
      // own clicks keeps them off whatever is underneath — the welcome video
      // treats a click as "skip".
      onClick={(e) => e.stopPropagation()}
    >
      {confirming ? (
        <div className="flex items-center gap-2 rounded-lg border border-white/15 bg-black/85 px-3 py-2 backdrop-blur">
          <span className="text-xs text-white/80">Close the assistant?</span>
          <button
            type="button"
            onClick={() => void closeWindow()}
            className="rounded-md bg-red-600/90 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-600"
          >
            Close
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            className="rounded-md px-2.5 py-1 text-xs text-white/70 hover:bg-white/10 hover:text-white"
          >
            Cancel
          </button>
        </div>
      ) : (
        <>
          <ControlButton
            label="Minimise"
            onClick={() => void minimizeWindow()}
          >
            <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden="true">
              <rect x="1.5" y="5.4" width="9" height="1.2" fill="currentColor" />
            </svg>
          </ControlButton>
          <ControlButton
            label="Close"
            danger
            onClick={() => setConfirming(true)}
          >
            <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden="true">
              <path
                d="M2 2l8 8M10 2l-8 8"
                stroke="currentColor"
                strokeWidth="1.3"
                strokeLinecap="round"
              />
            </svg>
          </ControlButton>
        </>
      )}
    </div>
  )
}

function ControlButton({
  label,
  onClick,
  danger,
  children,
}: {
  label: string
  onClick: () => void
  danger?: boolean
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      // Dim until reached for. These sit over a title sequence and over the
      // chatbot; a bright chrome strip in the corner of both would be the
      // first thing anybody looked at.
      className={`flex h-7 w-9 items-center justify-center rounded-md text-white/45 opacity-60 transition-all hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/60 ${
        danger ? "hover:bg-red-600 hover:text-white" : "hover:bg-white/15 hover:text-white"
      }`}
    >
      {children}
    </button>
  )
}
