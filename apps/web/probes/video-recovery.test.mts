import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import test from 'node:test'
import type { Peer } from 'peerjs'
import {
  RoomAccessError,
  RoomCall,
  type CallState,
  type RoomConnection,
} from '../src/features/video/media/connection.ts'

class TestPeer extends EventEmitter {
  destroy() {
    this.emit('close')
  }
}

test('renewal keeps the same peer and local tracks past the original join deadline', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const peer = new TestPeer()
  let created = 0
  let renewed = 0
  let stopped = 0
  const states: CallState[] = []
  const initial = Date.now()
  let deny = false
  const room = new RoomCall(
    {
      signalling: { secure: true },
      async acquire() {
        return {
          peerId: 'same-peer',
          token: 'same-token',
          expiresAt: initial + 60000,
          iceServers: [],
        }
      },
      async renew(grant) {
        assert.equal(grant.peerId, 'same-peer')
        assert.equal(grant.token, 'same-token')
        renewed++
        if (deny) throw new RoomAccessError('Access revoked')
        return Date.now() + 60000
      },
      async counterpart() {
        return null
      },
    },
    'doctor',
    {
      state: (state) => states.push(state),
      remote: () => {},
    },
    async () => {
      created++
      return peer as unknown as Peer
    },
  )
  await room.start({
    getTracks: () => [{ stop: () => stopped++ }],
  } as unknown as MediaStream)
  peer.emit('open')
  for (let i = 0; i < 4; i++) {
    t.mock.timers.tick(20000)
    await Promise.resolve()
    await Promise.resolve()
  }
  assert.ok(Date.now() > initial + 60000)
  assert.equal(created, 1)
  assert.equal(renewed, 4)
  assert.equal(stopped, 0)
  assert.equal(states.includes('reconnecting'), false)
  deny = true
  t.mock.timers.tick(20000)
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(states.at(-1), 'disconnected')
  assert.equal(stopped, 1)
  t.mock.timers.tick(30000)
  assert.equal(renewed, 5)
})

test('temporary renewal failures preserve the call until the active lease expires', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] })
  const peer = new TestPeer()
  const states: CallState[] = []
  let stopped = 0
  const room = new RoomCall(
    {
      signalling: { secure: true },
      async acquire() {
        return {
          peerId: 'peer',
          token: 'token',
          expiresAt: Date.now() + 60000,
          iceServers: [],
        }
      },
      async renew() {
        throw new Error('Network unavailable')
      },
      async counterpart() {
        return null
      },
    },
    'doctor',
    { state: (state) => states.push(state), remote: () => {} },
    async () => peer as unknown as Peer,
  )
  await room.start({
    getTracks: () => [{ stop: () => stopped++ }],
  } as unknown as MediaStream)
  peer.emit('open')
  t.mock.timers.tick(20000)
  await Promise.resolve()
  await Promise.resolve()
  assert.equal(states.at(-1), 'waiting')
  t.mock.timers.tick(40000)
  assert.equal(states.at(-1), 'reconnecting')
  assert.equal(stopped, 0)
  room.stop('left')
  assert.equal(stopped, 1)
})

test('reconnect uses a fresh assignment, ignores old events and stops on denial', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const peers: TestPeer[] = []
  const paths: string[] = []
  const states: CallState[] = []
  let attempts = 0
  let stops = 0
  const connection: RoomConnection = {
    signalling: { host: 'localhost', key: 'telelink', secure: true },
    async acquire() {
      attempts++
      if (attempts === 2) throw new Error('Temporary outage')
      if (attempts === 4) throw new RoomAccessError('Consultation completed')
      return {
        peerId: `peer-${attempts}`,
        token: `grant-${attempts}`,
        expiresAt: Date.now() + 60000,
        iceServers: [],
        signallingPath: `/peerjs/nodes/${attempts}`,
      }
    },
    async counterpart() {
      return null
    },
  }
  const stream = {
    getTracks: () => [{ stop: () => stops++ }],
  } as unknown as MediaStream
  const room = new RoomCall(
    connection,
    'doctor',
    {
      state: (value) => states.push(value),
      remote: () => {},
    },
    async (grant) => {
      const peer = new TestPeer()
      peers.push(peer)
      paths.push(grant.signallingPath!)
      return peer as unknown as Peer
    },
  )
  const tick = async (ms: number) => {
    t.mock.timers.tick(ms)
    await Promise.resolve()
    await Promise.resolve()
  }

  await room.start(stream)
  peers[0].emit('open')
  peers[0].emit('disconnected')
  assert.equal(states.at(-1), 'reconnecting')
  assert.equal(stops, 0)
  await tick(1201)
  assert.equal(attempts, 2)
  await tick(2401)
  assert.deepEqual(paths, ['/peerjs/nodes/1', '/peerjs/nodes/3'])
  peers[1].emit('open')
  peers[0].emit('disconnected')
  assert.equal(states.at(-1), 'waiting')
  peers[1].emit('disconnected')
  await tick(4801)
  assert.equal(states.at(-1), 'disconnected')
  assert.equal(stops, 1)
  await tick(30000)
  assert.equal(attempts, 4)
})

test('leaving cancels the pending retry and stops local media', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let attempts = 0
  let stops = 0
  const room = new RoomCall(
    {
      signalling: { secure: true },
      async acquire() {
        attempts++
        throw new Error('No server available')
      },
      async counterpart() {
        return null
      },
    },
    'doctor',
    { state: () => {}, remote: () => {} },
  )
  await room.start({
    getTracks: () => [{ stop: () => stops++ }],
  } as unknown as MediaStream)
  room.stop('left')
  t.mock.timers.tick(30000)
  assert.equal(attempts, 1)
  assert.equal(stops, 1)
})
