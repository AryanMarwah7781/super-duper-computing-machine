import { AlertTriangle } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

const SEVERE = new Set(["DANGER", "WARNING"])

export function SafetyBanner({ level, text }: { level: string; text: string }) {
  const severe = SEVERE.has(level)
  return (
    <Alert
      variant={severe ? "destructive" : "default"}
      className={`my-4 border-l-4 p-4 ${
        severe ? "border-l-destructive" : "border-l-amber-500"
      }`}
    >
      <AlertTriangle className="size-5" />
      <AlertTitle className="text-base font-bold tracking-wide">
        {level}
      </AlertTitle>
      <AlertDescription className="text-base text-foreground">
        {text}
      </AlertDescription>
    </Alert>
  )
}
