/** JoinPanel — the hosted-session dialog: giant room code, the join URL a
 * phone should open (plus a QR of it), and the live participant roster.
 * Purely presentational — session lifecycle (create/end/socket) stays in
 * PlayMode; ending is confirmed here and executed by the caller. */
import { clsx } from 'clsx'
import { UserX } from 'lucide-react'
import { useState } from 'react'

import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Dialog } from '@/components/ui/Dialog'
import { money } from '@/lib/format'
import { joinUrl, type HostCommand, type SessionSnapshot } from '@/lib/live'

import { JoinQr } from './JoinInfo'

export interface JoinPanelProps {
  open: boolean
  code: string
  /** LAN addresses the backend is reachable on (may be empty in browser dev). */
  lanIps: string[]
  /** Public tunnel origin while remote play is on (desktop only). */
  remoteUrl?: string | null
  /** Latest host-socket snapshot — null until the welcome arrives. */
  snapshot: SessionSnapshot | null
  /** Sends a host command over the live socket (kick, here). */
  command: (command: HostCommand, target?: string) => void
  /** Confirmed 'End session' — the caller tears everything down. */
  onEnd: () => void
  onClose: () => void
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-accent mb-1.5 text-[11px] font-bold tracking-widest uppercase">
      {children}
    </p>
  )
}

export function JoinPanel({
  open,
  code,
  lanIps,
  remoteUrl = null,
  snapshot,
  command,
  onEnd,
  onClose,
}: JoinPanelProps) {
  const [confirmEnd, setConfirmEnd] = useState(false)

  // Remote tunnel active → its URL serves everyone; wifi listed as alternate.
  // In browser dev the backend may report no LAN IPs — the page origin works.
  const lanPrimary = joinUrl(lanIps[0])
  const primaryUrl = remoteUrl ? `${remoteUrl}/join` : lanPrimary
  const extraUrls = [
    ...(remoteUrl ? [`on this wifi: ${lanPrimary}`] : []),
    ...lanIps.slice(1).map((ip) => `or ${joinUrl(ip)}`),
  ]

  const participants = snapshot?.participants ?? []
  // Board score by name — every participant is a board player by contract.
  const scores = new Map((snapshot?.scoreboard ?? []).map((p) => [p.name, p.score] as const))

  return (
    <>
      <Dialog open={open} onClose={onClose} title="Hosted game" className="w-full max-w-xl">
        <div className="flex flex-col items-center gap-6 px-6 py-5 sm:flex-row sm:items-start">
          <div className="flex min-w-0 flex-1 flex-col gap-5">
            <div>
              <SectionLabel>Room code</SectionLabel>
              <p className="font-display text-dollar text-5xl font-bold tracking-widest">
                {code}
              </p>
            </div>
            <div>
              <SectionLabel>{remoteUrl ? 'Join from anywhere' : 'On your phone, open'}</SectionLabel>
              <p className="text-ink font-mono text-sm break-all">{primaryUrl}</p>
              {extraUrls.map((u) => (
                <p key={u} className="text-ink-faint mt-0.5 font-mono text-xs break-all">
                  {u}
                </p>
              ))}
            </div>
          </div>

          <JoinQr url={primaryUrl} className="w-40" />
        </div>

        {/* Live roster — driven entirely by the host-socket snapshot */}
        <div className="border-line-soft border-t px-6 py-4">
          <SectionLabel>Players</SectionLabel>
          {participants.length === 0 ? (
            <p className="text-ink-muted text-sm">
              Waiting for players — scan or type the address, then enter code {code}.
            </p>
          ) : (
            <ul className="grid gap-x-8 gap-y-1.5 sm:grid-cols-2">
              {participants.map((p) => {
                const score = scores.get(p.name)
                return (
                  <li key={p.name} className="flex min-w-0 items-center gap-2 text-sm">
                    <span
                      className={clsx(
                        'size-2 shrink-0 rounded-full',
                        p.connected ? 'bg-accent' : 'bg-ink-faint',
                      )}
                      title={p.connected ? 'Connected' : 'Disconnected'}
                    />
                    <span
                      className={clsx(
                        'min-w-0 flex-1 truncate',
                        p.connected ? 'text-ink' : 'text-ink-muted',
                      )}
                    >
                      {p.name}
                    </span>
                    {score !== undefined && (
                      <span className="text-dollar shrink-0 font-semibold">{money(score)}</span>
                    )}
                    {/* No confirm — kicking is low-stakes: scores stay, they
                        can rejoin as themselves from the roster picker. */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => command('kick', p.name)}
                      title="Disconnect — they can rejoin as themselves"
                      aria-label={`Disconnect ${p.name}`}
                      className="-my-1 shrink-0 border-transparent px-1.5"
                    >
                      <UserX className="size-3.5" />
                    </Button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <div className="border-line-soft bg-surface/40 flex items-center justify-between border-t px-6 py-3.5">
          <Button variant="danger" onClick={() => setConfirmEnd(true)}>
            End session
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </Dialog>

      <ConfirmDialog
        open={confirmEnd}
        title="End session"
        message="Disconnect all players and close the room? Scores stay on the board."
        confirmLabel="End session"
        danger
        onConfirm={() => {
          setConfirmEnd(false)
          onEnd()
        }}
        onCancel={() => setConfirmEnd(false)}
      />
    </>
  )
}
