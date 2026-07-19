import { clsx } from 'clsx'

export function Spinner({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'size-5 animate-spin rounded-full border-2 border-line border-t-accent',
        className,
      )}
      role="status"
      aria-label="Loading"
    />
  )
}
