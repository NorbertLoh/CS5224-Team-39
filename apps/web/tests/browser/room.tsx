// Test-only entry: Vite's production build still includes only index.html.
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { VideoRoom } from '../../src/features/video/VideoRoom'
import type { RoomConnection } from '../../src/features/video/connection'
import '../../src/index.css'

const params = new URLSearchParams(location.search)
const role = params.get('role') === 'doctor' ? 'doctor' : 'patient'
sessionStorage.setItem(
  'telelink.session',
  JSON.stringify({
    accessToken: 'u11-test-only',
    refreshToken: 'test',
    expiresAt: Date.now() + 3600000,
  }),
)
const connection: RoomConnection = {
  signalling: {
    host: 'localhost',
    port: 8443,
    path: '/peerjs',
    key: 'telelink',
    secure: true,
  },
  async acquire(signal) {
    const response = await fetch('/u11-fixture/admissions', {
      method: 'POST',
      signal,
      headers: {
        authorization: `Bearer fixture-${role}-a`,
        'content-type': 'application/json',
      },
      body: JSON.stringify({ appointment_id: 'a' }),
    })
    if (!response.ok) throw new Error('Fixture admission denied')
    const grant = await response.json()
    const ice = await (await fetch('/u11-fixture/ice', { signal })).json()
    return {
      peerId: grant.peer_id,
      token: grant.token,
      expiresAt: params.has('shortLease')
        ? Date.now() + 1200
        : Date.parse(grant.expires_at),
      iceServers: ice.servers,
      relayOnly: ice.relay,
    }
  },
  async counterpart(_grant, signal) {
    const response = await fetch(`/u11-fixture/counterpart?role=${role}`, {
      signal,
    })
    if (!response.ok) throw new Error('Fixture discovery unavailable')
    return (await response.json()).peerId
  },
}
const client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: Infinity } },
})
const appointment = {
  appointment_id: 'u11-appointment',
  tenant_id: 'u11-clinic',
  patient_id: 'u11-patient',
  doctor_id: 'u11-doctor',
  status: 'in_progress',
  starts_at: '2026-10-18T10:00:00Z',
}
client.setQueryData(['identity', 'u11-test-only'], {
  subject_id: 'u11-doctor',
  global_roles: [],
  memberships: [
    { tenant_id: 'u11-clinic', roles: ['doctor'], status: 'active' },
  ],
})
client.setQueryData(['records', 'appointments', 'u11-test-only'], {
  pages: [{ items: [appointment], next_cursor: null }],
  pageParams: [null],
})
client.setQueryData(
  ['records', 'context', 'u11-test-only', 'u11-appointment'],
  appointment,
)
client.setQueryData(
  ['records', 'workspace', 'u11-test-only', 'u11-appointment'],
  { note: null, prescription: null },
)
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <VideoRoom role={role} connection={connection} />
    </QueryClientProvider>
  </StrictMode>,
)
