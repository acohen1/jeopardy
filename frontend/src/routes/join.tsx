import { createFileRoute } from '@tanstack/react-router'
import { useState, type ReactNode } from 'react'

import { ControllerScreen } from '@/components/controller/ControllerScreen'
import { JoinScreen } from '@/components/controller/JoinScreen'
import { readLastJoin, saveLastJoin } from '@/components/controller/lastJoin'
import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { clearPlayerToken, usePlayerSocket } from '@/lib/live'

export const Route = createFileRoute('/join')({
  component: JoinPage,
})

/** Phone controller: join form → giant buzzer. Lives at /join so the QR
 * code on the host screen lands straight here. Everything is mobile-first;
 * reconnection and identity are handled inside usePlayerSocket. */
function JoinPage() {
  // Stable object in state → the socket effect only re-runs on (re)join.
  const [join, setJoin] = useState<{ code: string; name: string } | null>(null)
  const { snapshot, phase, error, ended, lastResult, buzz } = usePlayerSocket(join)

  const handleJoin = (code: string, name: string) => {
    // A token from a previous life would hijack identity if the player now
    // wants a different name — only keep it when the name matches.
    if (readLastJoin().name !== name) clearPlayerToken()
    saveLastJoin(code, name)
    setJoin({ code, name })
  }

  // Guard on `join` too: the hook's state only resets on the next join, so
  // `ended` (and friends) go stale once we've cleared the join state.
  if (join && ended) {
    return (
      <Shell>
        <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
          <p className="text-5xl" aria-hidden>
            👋
          </p>
          <h1 className="font-display text-ink text-2xl font-bold">
            The host ended the game — thanks for playing!
          </h1>
          <Button
            variant="primary"
            size="lg"
            className="h-14 w-full max-w-xs text-lg"
            onClick={() => {
              clearPlayerToken()
              setJoin(null)
            }}
          >
            Join another
          </Button>
        </div>
      </Shell>
    )
  }

  // Fatal join error (bad code / name taken): the socket stops retrying, so
  // fall back to the form with the message inline and let them try again.
  if (!join || error) {
    return (
      <Shell>
        <JoinScreen error={join ? error : null} onJoin={handleJoin} />
      </Shell>
    )
  }

  if (!snapshot) {
    return (
      <Shell>
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <Spinner className="size-10" />
          <p className="text-ink-muted text-lg">Joining…</p>
        </div>
      </Shell>
    )
  }

  return (
    <Shell>
      <ControllerScreen
        you={join.name}
        snapshot={snapshot}
        phase={phase}
        lastResult={lastResult}
        buzz={buzz}
      />
    </Shell>
  )
}

/** Full-height mobile frame with the ever-present reconnect hint. */
function Shell({ children }: { children: ReactNode }) {
  return (
    <div className="bg-bg flex flex-1 flex-col">
      {children}
      <p className="text-ink-faint px-6 pt-1 pb-3 text-center text-xs">
        Keep this tab open — reconnects automatically.
      </p>
    </div>
  )
}
