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
