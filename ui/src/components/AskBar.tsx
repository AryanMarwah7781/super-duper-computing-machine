import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function AskBar({
  onAsk,
  busy,
  disabled,
}: {
  onAsk: (q: string) => void
  busy: boolean
  disabled: boolean
}) {
  const [value, setValue] = useState("")
  return (
    <form
      className="flex gap-3 border-t bg-card px-6 py-4"
      onSubmit={(e) => {
        e.preventDefault()
        if (value.trim()) {
          onAsk(value.trim())
          setValue("")
        }
      }}
    >
      <Input
        value={value}
        disabled={disabled}
        placeholder="Ask about the R4045…"
        className="h-12 text-lg"
        onChange={(e) => setValue(e.target.value)}
      />
      <Button
        type="submit"
        disabled={disabled || busy}
        className="h-12 px-8 text-lg"
      >
        {busy ? "Asking…" : "Ask"}
      </Button>
    </form>
  )
}
