export function Step({ num, text }: { num: string; text: string }) {
  return (
    <div className="flex gap-4 py-3">
      <div
        className="flex size-9 shrink-0 items-center justify-center rounded-full
                   bg-primary text-lg font-semibold text-primary-foreground"
      >
        {num}
      </div>
      <p className="pt-1 text-lg leading-relaxed">{text}</p>
    </div>
  )
}
