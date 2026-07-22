import { useEffect, useState } from 'react'

import { readLastJoin } from '@/components/controller/lastJoin'
import { Button } from '@/components/ui/Button'
import { TextInput } from '@/components/ui/TextInput'
import { money } from '@/lib/format'
import { fetchRoster, type RosterEntry } from '@/lib/live'

interface JoinScreenProps {
  /** Fatal join error from the socket (bad code / name taken), if any. */
  error: string | null
  onJoin: (code: string, name: string) => void
}

/** Mobile-first join form: room code + name, prefilled from the last join.
 * A 4-letter code triggers a debounced roster lookup — known players get a
 * one-tap "Who are you?" picker; "Someone new" (or no roster) falls back to
 * the classic free-text name flow. */
export function JoinScreen({ error, onJoin }: JoinScreenProps) {
  const [last] = useState(readLastJoin)
  const [code, setCode] = useState(last.code)
  const [name, setName] = useState(last.name)
  const [roster, setRoster] = useState<RosterEntry[] | null>(null)
  // "Someone new" collapses the picker back to the free-text name input.
  const [someoneNew, setSomeoneNew] = useState(false)

  const cleanCode = code.trim().toUpperCase()
  const cleanName = name.trim()
  const canJoin = cleanCode.length === 4 && cleanName.length > 0

  // Debounced roster lookup once the code holds 4 letters; re-runs on every
  // code change and after a join error (name claimed in a race → fresh list).
  // The cleanup flag drops stale responses from an out-of-date code.
  useEffect(() => {
    setRoster(null)
    setSomeoneNew(false)
    if (cleanCode.length !== 4) return
    let stale = false
    const timer = window.setTimeout(() => {
      void fetchRoster(cleanCode).then((entries) => {
        if (!stale) setRoster(entries)
      })
    }, 300)
    return () => {
      stale = true
      window.clearTimeout(timer)
    }
  }, [cleanCode, error])

  // Free-text is the fallback for everything: no roster yet (fetch in flight
  // or failed), an empty roster, or an explicit "Someone new".
  const showPicker = !someoneNew && roster != null && roster.length > 0

  return (
    <form
      className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-6 px-6 py-10"
      onSubmit={(e) => {
        e.preventDefault()
        // No submit while the picker is up — Enter in the code field must not
        // join as the stale prefilled name.
        if (!showPicker && canJoin) onJoin(cleanCode, cleanName)
      }}
    >
      <div className="text-center">
        <p className="text-ink-muted text-sm tracking-wide">Chaewon Jeopardy</p>
        <h1 className="font-display text-ink mt-1 text-3xl font-bold">Join the game</h1>
      </div>

      <label className="flex flex-col gap-2">
        <span className="text-ink-muted text-base">Room code</span>
        <TextInput
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z]/g, ''))}
          autoFocus
          inputMode="text"
          autoCapitalize="characters"
          autoCorrect="off"
          autoComplete="off"
          spellCheck={false}
          maxLength={4}
          placeholder="ABCD"
          aria-label="Room code"
          className="font-display h-16 text-center text-3xl font-bold tracking-widest uppercase"
        />
      </label>

      {showPicker ? (
        <div className="flex flex-col gap-2">
          <span className="text-ink-muted text-base">Who are you?</span>
          <ul className="flex flex-col gap-2">
            {roster.map((p) => (
              <li key={p.name}>
                <Button
                  variant="soft"
                  size="lg"
                  data-testid={`roster-pick-${p.name}`}
                  disabled={p.connected}
                  onClick={() => onJoin(cleanCode, p.name)}
                  className="h-14 w-full justify-between text-lg"
                >
                  <span className="min-w-0 truncate">{p.name}</span>
                  <span className="flex shrink-0 items-baseline gap-2">
                    <span className="text-dollar font-semibold">{money(p.score)}</span>
                    {p.connected && (
                      <span className="text-ink-faint text-xs font-normal">playing</span>
                    )}
                  </span>
                </Button>
              </li>
            ))}
          </ul>
          <Button
            variant="ghost"
            size="lg"
            data-testid="roster-new"
            onClick={() => setSomeoneNew(true)}
            className="h-12 w-full"
          >
            Someone new
          </Button>
        </div>
      ) : (
        <label className="flex flex-col gap-2">
          <span className="text-ink-muted text-base">Your name</span>
          <TextInput
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoCapitalize="words"
            autoComplete="off"
            maxLength={24}
            placeholder="Your name"
            aria-label="Your name"
            className="h-14 text-lg"
          />
        </label>
      )}

      {error && (
        <p className="text-danger text-center text-base" role="alert">
          {error}
        </p>
      )}

      {!showPicker && (
        <Button type="submit" variant="primary" size="lg" disabled={!canJoin} className="h-14 w-full text-lg">
          Join
        </Button>
      )}
    </form>
  )
}
