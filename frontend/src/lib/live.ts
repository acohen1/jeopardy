/** Live-session protocol + reconnecting WebSocket client.
 *
 * THE shared contract between the host UI and the phone controller —
 * mirrors backend/app/routers/live.py exactly. Transport-agnostic by
 * design: a future remote-play relay swaps the URL, not the protocol.
 *
 * Reconnect model (phones sleep, lock, and drop wifi constantly):
 * LiveSocket re-dials with capped exponential backoff and re-sends its
 * hello — players include their token, so identity survives any number
 * of drops. Every (re)connect yields a fresh authoritative snapshot in
 * the welcome, so no client state can go stale.
 */
import { useEffect, useRef, useState } from 'react'

// ------------------------------------------------------------------ //
//  Protocol types                                                     //
// ------------------------------------------------------------------ //
export type BuzzerState =
  | { phase: 'locked' }
  | { phase: 'armed'; lockedOut: string[] }
  | { phase: 'won'; winner: string; order: string[]; lockedOut: string[] }

export interface SessionSnapshot {
  code: string
  boardId: string
  participants: { name: string; connected: boolean }[]
  /** Every board player (phone-connected or not), in board order — joining a
   * session auto-creates/adopts a scoreboard player, so buzz winners can be
   * awarded by name and phones can render scores + standings. */
  scoreboard: { name: string; score: number; connected: boolean }[]
  /** Whose pick it is (board control under the turn rules), or null. */
  control: string | null
  buzzer: BuzzerState
}

export interface SessionCreated {
  code: string
  hostKey: string
  boardId: string
  lanIps: string[]
}

export type HostCommand =
  | 'arm'
  | 'disarm'
  | 'rearm-excluding-winner'
  | 'reset-buzzer'
  | 'end-session'
  /** With target: remove that participant (slot + token; scores untouched). */
  | 'kick'

type Hello =
  | { type: 'hello-host'; hostKey: string }
  | { type: 'hello-player'; code: string; name: string; token?: string }

export type ServerMessage =
  | { type: 'welcome'; token?: string; snapshot: SessionSnapshot }
  | { type: 'snapshot'; snapshot: SessionSnapshot }
  /** An award just happened (delta may be negative) — drives result flashes.
   * Carries the fresh snapshot so no follow-up round-trip is needed. */
  | { type: 'result'; player: string; delta: number; snapshot: SessionSnapshot }
  | { type: 'error'; message: string }
  | { type: 'ended' }

export type ConnectionPhase = 'connecting' | 'open' | 'reconnecting' | 'closed'

// ------------------------------------------------------------------ //
//  REST helpers                                                       //
// ------------------------------------------------------------------ //
import { api } from '@/api/client'

export const createSession = (boardId: string) =>
  api.post<SessionCreated>('/api/session', { board_id: boardId })
export const endSession = () => api.delete('/api/session')

export interface RosterEntry {
  name: string
  score: number
  connected: boolean
}

/** Pre-join "who are you?" lookup for a room code. `connected` names are
 * claimed by a live device; the rest are selectable (incl. your own slot
 * after a phone death). null = no session with that code. */
export async function fetchRoster(code: string): Promise<RosterEntry[] | null> {
  try {
    return await api.get<RosterEntry[]>(
      `/api/session/roster?code=${encodeURIComponent(code.trim().toUpperCase())}`,
    )
  } catch {
    return null
  }
}

export function wsUrl(): string {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/api/ws`
}

/** Join URL a phone should open (page origin already carries host:port). */
export function joinUrl(lanIp?: string): string {
  const { protocol, port, hostname } = window.location
  const host = lanIp ?? hostname
  return `${protocol}//${host}${port ? `:${port}` : ''}/join`
}

// ------------------------------------------------------------------ //
//  Reconnecting socket                                                //
// ------------------------------------------------------------------ //
export interface LiveSocketHandlers {
  onSnapshot: (snapshot: SessionSnapshot) => void
  onWelcome?: (token: string | undefined, snapshot: SessionSnapshot) => void
  onResult?: (player: string, delta: number) => void
  onError?: (message: string) => void
  onEnded?: () => void
  onPhase?: (phase: ConnectionPhase) => void
}

export class LiveSocket {
  private ws: WebSocket | null = null
  private closedByUs = false
  private attempt = 0
  private timer: number | null = null

  constructor(
    private makeHello: () => Hello,
    private handlers: LiveSocketHandlers,
  ) {}

  connect(): void {
    this.closedByUs = false
    this.dial()
  }

  private dial(): void {
    this.handlers.onPhase?.(this.attempt === 0 ? 'connecting' : 'reconnecting')
    const ws = new WebSocket(wsUrl())
    this.ws = ws

    ws.onopen = () => {
      this.attempt = 0
      ws.send(JSON.stringify(this.makeHello()))
    }
    ws.onmessage = (event) => {
      let msg: ServerMessage
      try {
        msg = JSON.parse(event.data as string) as ServerMessage
      } catch {
        return
      }
      // Version-skew tolerance (stale dev backend, future relay): a snapshot
      // missing newer fields must degrade, never crash `.map` in the UI.
      if ('snapshot' in msg && msg.snapshot) {
        msg.snapshot.scoreboard ??= []
        msg.snapshot.participants ??= []
        msg.snapshot.control ??= null
      }
      if (msg.type === 'welcome') {
        this.handlers.onPhase?.('open')
        this.handlers.onWelcome?.(msg.token, msg.snapshot)
        this.handlers.onSnapshot(msg.snapshot)
      } else if (msg.type === 'snapshot') {
        this.handlers.onSnapshot(msg.snapshot)
      } else if (msg.type === 'result') {
        this.handlers.onSnapshot(msg.snapshot)
        this.handlers.onResult?.(msg.player, msg.delta)
      } else if (msg.type === 'error') {
        this.closedByUs = true // fatal (bad code/name/key) — don't retry
        this.handlers.onError?.(msg.message)
      } else if (msg.type === 'ended') {
        this.closedByUs = true
        this.handlers.onEnded?.()
      }
    }
    ws.onclose = () => {
      this.ws = null
      if (this.closedByUs) {
        this.handlers.onPhase?.('closed')
        return
      }
      // capped exponential backoff: 0.5s, 1s, 2s, 4s, then every 5s
      const delay = Math.min(500 * 2 ** this.attempt, 5000)
      this.attempt += 1
      this.handlers.onPhase?.('reconnecting')
      this.timer = window.setTimeout(() => this.dial(), delay)
    }
    ws.onerror = () => {
      ws.close()
    }
  }

  send(
    message:
      | { type: 'buzz' }
      | { type: 'command'; command: HostCommand; target?: string },
  ): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  close(): void {
    this.closedByUs = true
    if (this.timer !== null) window.clearTimeout(this.timer)
    this.ws?.close()
    this.ws = null
    this.handlers.onPhase?.('closed')
  }
}

// ------------------------------------------------------------------ //
//  Hooks                                                              //
// ------------------------------------------------------------------ //
export interface LiveState {
  snapshot: SessionSnapshot | null
  phase: ConnectionPhase
  error: string | null
  ended: boolean
  /** Most recent award event; `at` keys the UI flash (new object per event). */
  lastResult: { player: string; delta: number; at: number } | null
}

/** Host-side stream: subscribe with the hostKey, send commands. */
export function useHostSocket(hostKey: string | null) {
  const [state, setState] = useState<LiveState>({
    snapshot: null,
    phase: 'closed',
    error: null,
    ended: false,
    lastResult: null,
  })
  const socketRef = useRef<LiveSocket | null>(null)

  useEffect(() => {
    if (!hostKey) return
    setState({ snapshot: null, phase: 'connecting', error: null, ended: false, lastResult: null })
    const socket = new LiveSocket(() => ({ type: 'hello-host', hostKey }), {
      onSnapshot: (snapshot) => setState((s) => ({ ...s, snapshot })),
      onResult: (player, delta) =>
        setState((s) => ({ ...s, lastResult: { player, delta, at: Date.now() } })),
      onError: (error) => setState((s) => ({ ...s, error })),
      onEnded: () => setState((s) => ({ ...s, ended: true })),
      onPhase: (phase) => setState((s) => ({ ...s, phase })),
    })
    socketRef.current = socket
    socket.connect()
    return () => {
      socketRef.current = null
      socket.close()
    }
  }, [hostKey])

  return {
    ...state,
    command: (command: HostCommand, target?: string) =>
      socketRef.current?.send({ type: 'command', command, target }),
  }
}

const PLAYER_TOKEN_KEY = 'live-player-token'

/** Player-side stream: join with code+name (or resume via stored token). */
export function usePlayerSocket(join: { code: string; name: string } | null) {
  const [state, setState] = useState<LiveState>({
    snapshot: null,
    phase: 'closed',
    error: null,
    ended: false,
    lastResult: null,
  })
  const socketRef = useRef<LiveSocket | null>(null)

  useEffect(() => {
    if (!join) return
    setState({ snapshot: null, phase: 'connecting', error: null, ended: false, lastResult: null })
    const socket = new LiveSocket(
      () => ({
        type: 'hello-player',
        code: join.code,
        name: join.name,
        token: localStorage.getItem(PLAYER_TOKEN_KEY) ?? undefined,
      }),
      {
        onSnapshot: (snapshot) => setState((s) => ({ ...s, snapshot })),
        onResult: (player, delta) =>
          setState((s) => ({ ...s, lastResult: { player, delta, at: Date.now() } })),
        onWelcome: (token) => {
          if (token) localStorage.setItem(PLAYER_TOKEN_KEY, token)
        },
        onError: (error) => setState((s) => ({ ...s, error })),
        onEnded: () => setState((s) => ({ ...s, ended: true })),
        onPhase: (phase) => setState((s) => ({ ...s, phase })),
      },
    )
    socketRef.current = socket
    socket.connect()
    return () => {
      socketRef.current = null
      socket.close()
    }
  }, [join])

  return {
    ...state,
    buzz: () => socketRef.current?.send({ type: 'buzz' }),
  }
}

/** Forget a stored player identity (e.g. before joining a fresh session). */
export function clearPlayerToken(): void {
  localStorage.removeItem(PLAYER_TOKEN_KEY)
}
