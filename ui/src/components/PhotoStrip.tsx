import { imageUrl, type ImageRef } from "@/lib/render"

export function Photo({
  caption,
  image,
}: {
  caption: string
  image: ImageRef | null
}) {
  // A marker with no matching image becomes its caption, never a broken icon.
  if (!image) {
    return <p className="my-2 text-sm italic text-muted-foreground">{caption}</p>
  }
  return (
    <figure className="my-4">
      <img
        src={imageUrl(image)}
        alt={caption}
        className="max-h-80 rounded-lg border bg-card object-contain"
      />
      <figcaption className="mt-1 text-sm text-muted-foreground">
        {caption}
      </figcaption>
    </figure>
  )
}
