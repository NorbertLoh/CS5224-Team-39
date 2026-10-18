import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { test } from 'node:test'
import type { MediaConnection, Peer } from 'peerjs'
import { RoomCall, validateAdmission } from '../src/features/video/connection'
import type {
  CallAdmission,
  CallState,
  RoomConnection,
} from '../src/features/video/connection'

const admission = (): CallAdmission => ({
  peerId: 'self',
  token: 'opaque',
  expiresAt: Date.now() + 60000,
  iceServers: [],
})
function stream() {
  const track = {
    readyState: 'live',
    stop() {
      this.readyState = 'ended'
    },
  }
  return {
    track,
    media: { getTracks: () => [track] } as unknown as MediaStream,
  }
}
class Call extends EventEmitter {
  peerConnection!: EventTarget & { connectionState: string }
  closed = false
  constructor(public peer: string) {
    super()
  }
  answer() {
    this.peerConnection = Object.assign(new EventTarget(), {
      connectionState: 'new',
    })
  }
  close() {
    this.closed = true
    if (this.peerConnection) this.peerConnection.connectionState = 'closed'
    this.emit('close')
  }
}
class Client extends EventEmitter {
  destroyed = false
  destroy() {
    this.destroyed = true
    this.emit('close')
  }
}
const tick = () => new Promise<void>((resolve) => setImmediate(resolve))
function fixture() {
  const peer = new Client()
  const local = stream()
  const states: CallState[] = []
  let remote: MediaStream | null = null
  const connection: RoomConnection = {
    signalling: {
      host: 'localhost',
      port: 8443,
      path: '/peerjs',
      key: 'telelink',
      secure: true,
    },
    acquire: async () => admission(),
    counterpart: async () => 'patient-peer',
  }
  const events = {
    state: (state: CallState) => states.push(state),
    remote: (value: MediaStream | null) => {
      remote = value
    },
  }
  const create = () =>
    new RoomCall(
      connection,
      'doctor',
      events,
      async () => peer as unknown as Peer,
    )
  return { peer, local, states, connection, create, remote: () => remote }
}

test('leaving during admission aborts the lookup and stops devices without opening a late peer', async () => {
  const f = fixture()
  let resolve!: (value: CallAdmission) => void
  let signal!: AbortSignal
  f.connection.acquire = (value) => {
    signal = value
    return new Promise((done) => {
      resolve = done
    })
  }
  const call = f.create()
  const starting = call.start(f.local.media)
  call.stop('left')
  resolve(admission())
  await starting
  assert.equal(signal.aborted, true)
  assert.equal(f.local.track.readyState, 'ended')
  assert.deepEqual(f.states, ['joining', 'left'])
})

test('an incoming call must match the resolved counterpart; incoming RTC is created during answer', async () => {
  const f = fixture()
  const room = f.create()
  await room.start(f.local.media)
  f.peer.emit('open')
  const wrong = new Call('other-peer')
  f.peer.emit('call', wrong as unknown as MediaConnection)
  await tick()
  assert.equal(wrong.closed, true)
  assert.equal(f.peer.destroyed, false)
  const correct = new Call('patient-peer')
  f.peer.emit('call', correct as unknown as MediaConnection)
  await tick()
  assert.ok(correct.peerConnection)
  correct.peerConnection.connectionState = 'connected'
  const incoming = stream()
  correct.emit('stream', incoming.media)
  assert.equal(f.states.at(-1), 'connected')
  assert.equal(f.remote(), incoming.media)
  f.peer.emit('disconnected')
  assert.equal(f.states.at(-1), 'disconnected')
  assert.equal(f.local.track.readyState, 'ended')
  assert.equal(incoming.track.readyState, 'ended')
  assert.equal(correct.closed, true)
  assert.equal(f.remote(), null)
})

test('expiring a lease closes media and a peer; later callbacks cannot resurrect the call', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 1000000 })
  const f = fixture()
  f.connection.acquire = async () => ({
    ...admission(),
    expiresAt: Date.now() + 100,
  })
  const call = f.create()
  await call.start(f.local.media)
  f.peer.emit('open')
  t.mock.timers.tick(100)
  assert.equal(f.states.at(-1), 'disconnected')
  assert.equal(f.peer.destroyed, true)
  assert.equal(f.local.track.readyState, 'ended')
  f.peer.emit('open')
  assert.equal(f.states.at(-1), 'disconnected')
})

test('invalid or expired admission and forced relay without TURN fail before media transmission', () => {
  assert.throws(() =>
    validateAdmission({ ...admission(), expiresAt: Date.now() - 1 }),
  )
  assert.throws(() => validateAdmission({ ...admission(), relayOnly: true }))
  assert.doesNotThrow(() =>
    validateAdmission({
      ...admission(),
      relayOnly: true,
      iceServers: [
        { urls: 'turn:localhost:3478', username: 'test', credential: 'test' },
      ],
    }),
  )
})

test('leaving while PeerJS loads destroys the late client and never installs a room', async () => {
  const f = fixture()
  let resolve!: (peer: Peer) => void
  const room = new RoomCall(
    f.connection,
    'doctor',
    { state: (s) => f.states.push(s), remote: () => {} },
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const starting = room.start(f.local.media)
  await tick()
  room.stop('left')
  resolve(f.peer as unknown as Peer)
  await starting
  assert.equal(f.peer.destroyed, true)
  assert.equal(f.local.track.readyState, 'ended')
  assert.equal(f.states.at(-1), 'left')
})
