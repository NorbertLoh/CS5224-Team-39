import { useEffect, useState } from 'react'
import { Tabs } from 'radix-ui'
import type { Appointment } from '../scheduling/api'
import { AppointmentGrid } from './AppointmentGrid'
import { LiveAppointmentDetails } from './LiveAppointmentDetails'

export function PatientAppointments({ appointments, token, subjectId }: {
  appointments: Appointment[]
  token?: string
  subjectId: string
}) {
  const [period, setPeriod] = useState('upcoming')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const isUpcoming = (appointment: Appointment) =>
    ['held', 'pending_payment', 'confirmed', 'in_progress'].includes(appointment.status)
    && Date.parse(appointment.ends_at) > now
  const groups = [
    {
      value: 'upcoming', label: 'Upcoming',
      items: appointments.filter(isUpcoming)
        .sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)),
    },
    {
      value: 'past', label: 'Past',
      items: appointments.filter((appointment) => !isUpcoming(appointment))
        .sort((a, b) => Date.parse(b.starts_at) - Date.parse(a.starts_at)),
    },
  ]

  return (
    <Tabs.Root value={period} onValueChange={(value) => {
      setPeriod(value)
      setSelectedId(null)
    }}>
      <Tabs.List aria-label="Appointment period" className="mb-5 flex w-fit gap-1 rounded-lg bg-slate-100 p-1">
        {groups.map((group) => (
          <Tabs.Trigger
            key={group.value}
            value={group.value}
            className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 data-[state=active]:bg-white data-[state=active]:text-slate-900 data-[state=active]:shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2"
          >
            {group.label} ({group.items.length})
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {groups.map((group) => (
        <Tabs.Content key={group.value} value={group.value} className="space-y-5 focus-visible:outline-2 focus-visible:outline-offset-2">
          {group.items.length ? (
            <AppointmentGrid
              appointments={group.items}
              date=""
              role="patient"
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ) : (
            <p role="status" className="text-slate-600">No {group.value} appointments.</p>
          )}
          {selectedId && group.items.some((appointment) => appointment.appointment_id === selectedId) && (
            <LiveAppointmentDetails
              key={selectedId}
              id={selectedId}
              token={token}
              subjectId={subjectId}
              role="patient"
              onClose={() => setSelectedId(null)}
            />
          )}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  )
}
