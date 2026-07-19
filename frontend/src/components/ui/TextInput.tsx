import { clsx } from 'clsx'
import type { InputHTMLAttributes } from 'react'

export function TextInput({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={clsx(
        'bg-surface text-ink placeholder:text-ink-faint rounded-lg border border-line px-3 py-1.5 text-sm',
        'focus:border-accent focus:outline-none',
        className,
      )}
      {...rest}
    />
  )
}
