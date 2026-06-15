import { cn } from '@/lib/utils'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// Brand badge: Huaqing mark — a styled "H" on a warm surface.
// Fills the tile (softly rounded); size via className (default size-14).
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-md bg-(--dt-primary) text-(--dt-primary-foreground)',
        className
      )}
      {...props}
    >
      <span className="text-2xl font-semibold tracking-tight" style={{ fontFamily: 'MiSans, sans-serif' }}>
        H
      </span>
    </span>
  )
}
