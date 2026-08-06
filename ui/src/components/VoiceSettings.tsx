import { useEffect, useState } from "react"
import { Mic, MicOff, Settings2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  audioDevices,
  setAudioDevice,
  startVoice,
  stopVoice,
  type AudioDevice,
} from "@/lib/bridge"
import type { VoiceState } from "@/hooks/useAssist"

/**
 * Microphone controls, in the application rather than a separate debug tool.
 *
 * Switching device restarts the audio stream, because a device cannot be
 * changed underneath an open one — so the list is only useful if picking from
 * it actually takes effect immediately, which it does.
 */
export function VoiceSettings({ state }: { state: VoiceState }) {
  const [open, setOpen] = useState(false)
  const [devices, setDevices] = useState<AudioDevice[]>([])
  const [current, setCurrent] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)

  const listening = state !== "off"

  useEffect(() => {
    if (!open) return
    void audioDevices().then((r) => {
      setDevices(r.devices)
      setCurrent(r.current)
    })
  }, [open, state])

  async function pick(index: number) {
    setBusy(true)
    setCurrent(index)
    await setAudioDevice(index)
    setBusy(false)
  }

  async function toggle() {
    setBusy(true)
    if (listening) await stopVoice()
    else await startVoice()
    setBusy(false)
  }

  return (
    <span className="relative">
      <Button
        variant="ghost"
        size="sm"
        className="h-7 gap-1.5 px-2 text-xs"
        onClick={() => setOpen((v) => !v)}
        aria-label="Microphone settings"
      >
        <Settings2 className="size-3.5" />
        mic
      </Button>

      {open && (
        <>
          {/* Click-away, so the panel does not need to be dismissed twice. */}
          <span className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div
            className="absolute bottom-9 right-0 z-50 w-80 rounded-xl border
                       bg-popover p-3 shadow-lg"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-foreground">
                Microphone
              </span>
              <Button
                variant={listening ? "outline" : "default"}
                size="sm"
                className="h-7 gap-1.5 px-2.5 text-xs"
                disabled={busy}
                onClick={toggle}
              >
                {listening ? (
                  <>
                    <MicOff className="size-3.5" />
                    Stop listening
                  </>
                ) : (
                  <>
                    <Mic className="size-3.5" />
                    Start listening
                  </>
                )}
              </Button>
            </div>

            <p className="mt-2 text-xs text-muted-foreground">
              {listening
                ? 'Listening for "hey chris".'
                : "Voice is off — nothing is being recorded."}
            </p>

            <div className="mt-3 max-h-56 space-y-1 overflow-y-auto">
              {devices.length === 0 && (
                <p className="px-1 text-xs text-muted-foreground">
                  No input devices found.
                </p>
              )}
              {devices.map((d) => (
                <button
                  key={d.index}
                  type="button"
                  disabled={busy}
                  onClick={() => void pick(d.index)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5
                              text-left text-xs transition hover:bg-accent
                              disabled:opacity-50 ${
                                d.index === current
                                  ? "bg-accent font-medium text-foreground"
                                  : "text-muted-foreground"
                              }`}
                >
                  <Mic className="size-3 shrink-0" />
                  <span className="truncate">{d.name}</span>
                  {d.default && (
                    <span className="ml-auto shrink-0 text-[10px] uppercase">
                      default
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </span>
  )
}
