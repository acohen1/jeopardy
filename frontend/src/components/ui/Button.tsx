import { clsx } from 'clsx'
import type { ButtonHTMLAttributes } from 'react'

export type ButtonVariant = 'primary' | 'soft' | 'ghost' | 'danger' | 'success' | 'deduct'
export type ButtonSize = 'sm' | 'md' | 'lg'

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-accent-deep text-ink border border-accent/60 hover:bg-accent hover:text-bg-deep font-bold',
  soft: 'bg-surface text-ink border border-line hover:bg-cell hover:border-accent/70',
  ghost:
    'bg-transparent text-ink-muted border border-line/60 hover:bg-surface hover:text-ink hover:border-line',
  danger:
    'bg-[#3a2828] text-[#ddaaaa] border border-[#5a3838] hover:bg-[#503535] hover:text-ink',
  success:
    'bg-[#283828] text-[#aaddaa] border border-accent-deep hover:bg-[#385038] hover:text-ink font-bold',
  deduct:
    'bg-[#382828] text-[#ddaaaa] border border-danger-deep hover:bg-[#503838] hover:text-ink font-bold',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'px-2.5 py-1 text-xs rounded-md gap-1',
  md: 'px-3.5 py-1.5 text-sm rounded-lg gap-1.5',
  lg: 'px-5 py-2.5 text-base rounded-lg gap-2',
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
}

export function Button({ variant = 'soft', size = 'md', className, type, ...rest }: ButtonProps) {
  return (
    <button
      type={type ?? 'button'}
      className={clsx(
        'inline-flex cursor-pointer items-center justify-center transition-colors duration-100',
        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
        'disabled:cursor-not-allowed disabled:opacity-45',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    />
  )
}
