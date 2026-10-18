import type { MediaConnection, Peer, PeerOptions } from 'peerjs'

export type CallState =
  | 'waiting'
  | 'joining'
  | 'connecting'
  | 'connected'
  | 'disconnected'
  | 'left'

export type CallAdmission = {
  peerId: string
  token: string
  expiresAt: number
  iceServers: RTCIceServer[]
  relayOnly?: boolean
}

// V04 supplies the authenticated admission/discovery adapter. No peer IDs, keys
// or bearer credentials are entered by room users or persisted by this component.
export type RoomConnection = {
  signalling: Pick<PeerOptions, 'host' | 'port' | 'path' | 'key'> & {
    secure: true
  }
  acquire: (signal: AbortSignal) => Promise<CallAdmission>
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
    for (const timer of this.timers) clearTimeout(timer)
    this.timers.clear()
    this.call?.close()
    this.peer?.destroy()
    this.stream?.getTracks().forEach((track) => track.stop())
    this.remote?.getTracks().forEach((track) => track.stop())
    this.peer = null
    this.call = null
    this.stream = null
    this.remote = null
    this.admission = null
    this.events.remote(null)
    if (state) this.events.state(state, message)
  }

  private fail = () =>
    this.stop(
      'disconnected',
      'The call was interrupted. Rejoin to reconnect securely.',
    )

  async start(stream: MediaStream) {
    this.stream = stream
    this.events.state('joining')
    const preparing = this.later(this.fail, 15000)
    try {
      const admission = await this.connection.acquire(this.abort.signal)
      if (!this.live()) return
      validateAdmission(admission)
      this.admission = admission
      this.later(
        () =>
          this.stop(
            'disconnected',
            'Your call access expired. Rejoin to request fresh access.',
          ),
        admission.expiresAt - Date.now(),
      )
      const peer = await this.factory(admission, this.connection)
      if (!this.live()) {
        peer.destroy()
        return
      }
      this.peer = peer
      clearTimeout(preparing)
      const opening = this.later(this.fail, 15000)
      peer.on('open', () => {
        if (!this.live()) return
        clearTimeout(opening)
        this.events.state('waiting')
        if (this.role === 'patient') void this.findCounterpart()
      })
      peer.on('call', (call) => {
        void this.answer(call)
      })
      peer.on('disconnected', this.fail)
      peer.on('close', this.fail)
      peer.on('error', this.fail)
    } catch {
      if (this.live()) this.fail()
    }
  }

  private async findCounterpart() {
    if (!this.admission || !this.peer || !this.live()) return
    try {
      const id = await this.connection.counterpart(
        this.admission,
        this.abort.signal,
      )
      if (!this.live()) return
      if (!id) {
        this.later(() => {
          void this.findCounterpart()
        }, 1000)
        return
      }
      if (id === this.admission.peerId) return this.fail()
      this.attach(this.peer.call(id, this.stream!))
    } catch {
      if (this.live()) this.fail()
    }
  }

  private async answer(call: MediaConnection) {
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
        this.abort.signal,
      )
      if (!this.live() || this.call || id !== call.peer) {
        call.close()
        return
      }
      this.attach(call, true)
    } catch {
      call.close()
      if (this.live()) this.fail()
    }
  }

  private attach(call: MediaConnection, answer = false) {
    this.call = call
    this.events.state('connecting')
    const connecting = this.later(this.fail, 15000)
    call.on('stream', (remote) => {
      if (!this.live()) {
        remote.getTracks().forEach((track) => track.stop())
        return
      }
      this.remote = remote
      this.events.remote(remote)
      if (call.peerConnection.connectionState === 'connected') {
        clearTimeout(connecting)
        this.events.state('connected')
      }
    })
    call.on('close', this.fail)
    call.on('error', this.fail)
    // Incoming PeerJS calls create their RTCPeerConnection during answer().
    if (answer) call.answer(this.stream!)
    call.peerConnection.addEventListener('connectionstatechange', () => {
      if (!this.live()) return
      const state = call.peerConnection.connectionState
      if (state === 'connected') {
        clearTimeout(connecting)
        if (this.remote) this.events.state('connected')
      } else if (['disconnected', 'failed', 'closed'].includes(state))
        this.fail()
    })
  }
}
