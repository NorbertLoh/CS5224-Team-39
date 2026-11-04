import type { MediaConnection, Peer, PeerOptions } from 'peerjs'

export type CallState =
  | 'waiting'
  | 'joining'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'reconnecting'
  | 'left'

export type CallAdmission = {
  peerId: string
  token: string
  expiresAt: number
  iceServers: RTCIceServer[]
  relayOnly?: boolean
  signallingPath?: string
}

// V04 supplies the authenticated admission/discovery adapter. No peer IDs, keys
// or bearer credentials are entered by room users or persisted by this component.
export type RoomConnection = {
  signalling: Pick<PeerOptions, 'host' | 'port' | 'path' | 'key'> & {
    secure: true
  }
  acquire: (signal: AbortSignal) => Promise<CallAdmission>
  renew?: (admission: CallAdmission, signal: AbortSignal) => Promise<number>
  counterpart: (
    admission: CallAdmission,
    signal: AbortSignal,
  ) => Promise<string | null>
}

type Events = {
  state: (state: CallState, message?: string) => void
  remote: (stream: MediaStream | null) => void
}
type PeerFactory = (
  admission: CallAdmission,
  connection: RoomConnection,
) => Promise<Peer>

export class RoomAccessError extends Error {}

export function validateAdmission(admission: CallAdmission, now = Date.now()) {
  if (
    !admission.peerId ||
    !admission.token ||
    !Number.isFinite(admission.expiresAt) ||
    admission.expiresAt <= now ||
    admission.expiresAt > now + 300000
  ) {
    throw new Error('Admission unavailable')
  }
  if (
    admission.relayOnly &&
    !admission.iceServers.some((server) =>
      [server.urls].flat().some((url) => /^turns?:/.test(url)),
    )
  ) {
    throw new Error('Relay configuration unavailable')
  }
}

async function createPeer(
  admission: CallAdmission,
  connection: RoomConnection,
) {
  const { Peer } = await import('peerjs')
  return new Peer(admission.peerId, {
    ...connection.signalling,
    path: admission.signallingPath ?? connection.signalling.path,
    token: admission.token,
    debug: 0,
    config: {
      bundlePolicy: 'max-bundle',
      iceServers: admission.iceServers,
      iceTransportPolicy: admission.relayOnly ? 'relay' : 'all',
    },
  })
}

export class RoomCall {
  private abort = new AbortController()
  private peer: Peer | null = null
  private call: MediaConnection | null = null
  private stream: MediaStream | null = null
  private remote: MediaStream | null = null
  private timers = new Set<ReturnType<typeof setTimeout>>()
  private admission: CallAdmission | null = null
  private attempt = 0
  private attemptAbort = new AbortController()
  private retrying = false
  private failures = 0
  private recoveryStarted: number | null = null
  private expiryTimer: ReturnType<typeof setTimeout> | null = null

  constructor(
    private connection: RoomConnection,
    private role: 'patient' | 'doctor',
    private events: Events,
    private factory: PeerFactory = createPeer,
  ) {}

  private live = () => !this.abort.signal.aborted

  private later(action: () => void, ms: number) {
    const timer = setTimeout(() => {
      this.timers.delete(timer)
      if (this.live()) action()
    }, ms)
    this.timers.add(timer)
    return timer
  }

  stop(state?: CallState, message?: string) {
    if (!this.live()) return
    this.abort.abort()
    this.closeAttempt()
    this.stream?.getTracks().forEach((track) => track.stop())
    this.stream = null
    if (state) this.events.state(state, message)
  }

  private closeAttempt() {
    this.attempt++
    this.attemptAbort.abort()
    for (const timer of this.timers) clearTimeout(timer)
    this.timers.clear()
    this.expiryTimer = null
    this.call?.close()
    this.peer?.destroy()
    this.remote?.getTracks().forEach((track) => track.stop())
    this.peer = null
    this.call = null
    this.remote = null
    this.admission = null
    this.events.remote(null)
  }

  private fail = () => {
    if (!this.live() || this.retrying) return
    this.recoveryStarted ??= Date.now()
    if (Date.now() - this.recoveryStarted >= 12 * 60 * 60 * 1000) {
      this.stop(
        'disconnected',
        'Could not reconnect. Rejoin when you are ready.',
      )
      return
    }
    this.retrying = true
    this.closeAttempt()
    this.events.state('reconnecting', 'Reconnecting securely…')
    const delay = Math.min(
      30000,
      (800 + Math.random() * 400) * 2 ** Math.min(this.failures++, 5),
    )
    this.later(() => {
      this.retrying = false
      void this.start(this.stream!)
    }, delay)
  }

  async start(stream: MediaStream) {
    if (!this.live()) return
    if (
      this.recoveryStarted !== null &&
      Date.now() - this.recoveryStarted >= 12 * 60 * 60 * 1000
    ) {
      this.stop(
        'disconnected',
        'Could not reconnect. Rejoin when you are ready.',
      )
      return
    }
    const attempt = ++this.attempt
    this.attemptAbort = new AbortController()
    const current = () => this.live() && attempt === this.attempt
    this.stream = stream
    if (this.recoveryStarted === null) this.events.state('joining')
    const preparing = this.later(this.fail, 15000)
    try {
      const admission = await this.connection.acquire(this.attemptAbort.signal)
      if (!current()) return
      validateAdmission(admission)
      this.admission = admission
      this.watchExpiry(admission)
      const peer = await this.factory(admission, this.connection)
      if (!current()) {
        peer.destroy()
        return
      }
      this.peer = peer
      clearTimeout(preparing)
      const opening = this.later(this.fail, 15000)
      peer.on('open', () => {
        if (!current()) return
        clearTimeout(opening)
        this.events.state('waiting')
        if (this.connection.renew) this.scheduleRenewal(admission, attempt)
        if (this.role === 'patient') void this.findCounterpart()
      })
      peer.on('call', (call) => {
        if (current()) void this.answer(call)
        else call.close()
      })
      const fail = () => {
        if (current()) this.fail()
      }
      peer.on('disconnected', fail)
      peer.on('close', fail)
      peer.on('error', fail)
    } catch (error) {
      if (current()) {
        if (error instanceof RoomAccessError)
          this.stop('disconnected', error.message)
        else this.fail()
      }
    }
  }

  private watchExpiry(admission: CallAdmission) {
    if (this.expiryTimer) {
      clearTimeout(this.expiryTimer)
      this.timers.delete(this.expiryTimer)
    }
    this.expiryTimer = this.later(this.fail, admission.expiresAt - Date.now())
  }

  private scheduleRenewal(
    admission: CallAdmission,
    attempt: number,
    retry = false,
  ) {
    const remaining = admission.expiresAt - Date.now()
    const delay = retry ? Math.min(2000, remaining / 4) : remaining / 3
    this.later(
      () => {
        void this.renew(admission, attempt)
      },
      Math.max(1, delay),
    )
  }

  private async renew(admission: CallAdmission, attempt: number) {
    const current = () => this.live() && attempt === this.attempt
    if (!current() || !this.connection.renew) return
    try {
      const expiresAt = await this.connection.renew(
        admission,
        this.attemptAbort.signal,
      )
      if (!current()) return
      validateAdmission({ ...admission, expiresAt })
      admission.expiresAt = Math.max(admission.expiresAt, expiresAt)
      this.watchExpiry(admission)
      this.scheduleRenewal(admission, attempt)
    } catch (error) {
      if (!current()) return
      if (error instanceof RoomAccessError)
        this.stop('disconnected', error.message)
      else if (Date.now() >= admission.expiresAt) this.fail()
      else this.scheduleRenewal(admission, attempt, true)
    }
  }

  private async findCounterpart() {
    if (!this.admission || !this.peer || !this.live()) return
    const attempt = this.attempt
    const current = () => this.live() && attempt === this.attempt
    try {
      const id = await this.connection.counterpart(
        this.admission,
        this.attemptAbort.signal,
      )
      if (!current()) return
      if (!id) {
        this.later(() => {
          void this.findCounterpart()
        }, 1000)
        return
      }
      if (id === this.admission.peerId) return this.fail()
      this.attach(this.peer.call(id, this.stream!))
    } catch {
      if (current()) this.fail()
    }
  }

  private async answer(call: MediaConnection) {
    const attempt = this.attempt
    const current = () => this.live() && attempt === this.attempt
    if (
      !this.live() ||
      !this.admission ||
      this.role !== 'doctor' ||
      this.call
    ) {
      call.close()
      return
    }
    try {
      const id = await this.connection.counterpart(
        this.admission,
        this.attemptAbort.signal,
      )
      if (!current() || this.call || id !== call.peer) {
        call.close()
        return
      }
      this.attach(call, true)
    } catch {
      call.close()
      if (current()) this.fail()
    }
  }

  private attach(call: MediaConnection, answer = false) {
    const attempt = this.attempt
    const current = () =>
      this.live() && attempt === this.attempt && this.call === call
    const connected = () => {
      this.failures = 0
      this.recoveryStarted = null
      this.events.state('connected')
    }
    this.call = call
    this.events.state('connecting')
    const connecting = this.later(this.fail, 15000)
    call.on('stream', (remote) => {
      if (!current()) {
        remote.getTracks().forEach((track) => track.stop())
        return
      }
      this.remote = remote
      this.events.remote(remote)
      if (call.peerConnection.connectionState === 'connected') {
        clearTimeout(connecting)
        connected()
      }
    })
    const fail = () => {
      if (current()) this.fail()
    }
    call.on('close', fail)
    call.on('error', fail)
    // Incoming PeerJS calls create their RTCPeerConnection during answer().
    if (answer) call.answer(this.stream!)
    call.peerConnection.addEventListener('connectionstatechange', () => {
      if (!current()) return
      const state = call.peerConnection.connectionState
      if (state === 'connected') {
        clearTimeout(connecting)
        if (this.remote) connected()
      } else if (['disconnected', 'failed', 'closed'].includes(state))
        this.fail()
    })
  }
}
