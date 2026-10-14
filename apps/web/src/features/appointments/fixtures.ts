import shared from '../../../../../dev/fixtures/telelink.json'

export type AppointmentRole = 'patient' | 'doctor' | 'clinic_admin'
export type Appointment = (typeof shared.appointments)[number]

export function dateInSingapore(instant: string) {
  return new Date(Date.parse(instant) + 8 * 3600000).toISOString().slice(0, 10)
}

export function previewContexts(role: AppointmentRole) {
  if (role === 'clinic_admin')
    return shared.clinics.map((clinic) => ({
      id: clinic.tenant_id,
      name: clinic.name,
    }))
  return shared.subjects
    .filter((subject) =>
      role === 'patient'
        ? subject.global_roles.includes('patient')
        : shared.memberships.some(
            (member) =>
              member.subject_id === subject.subject_id &&
              member.status === 'active' &&
              member.roles.includes('doctor'),
          ),
    )
    .map((subject) => ({ id: subject.subject_id, name: subject.display_name }))
}

export function scopedAppointments(
  role: AppointmentRole,
  contextId: string,
  tenantId?: string,
) {
  return shared.appointments
    .filter((appointment) => {
      if (tenantId && appointment.tenant_id !== tenantId) return false
      if (role === 'patient') return appointment.patient_id === contextId
      if (role === 'clinic_admin') return appointment.tenant_id === contextId
      return (
        appointment.doctor_id === contextId &&
        shared.memberships.some(
          (member) =>
            member.subject_id === contextId &&
            member.tenant_id === appointment.tenant_id &&
            member.status === 'active' &&
            member.roles.includes('doctor'),
        )
      )
    })
    .sort(
      (a, b) =>
        a.starts_at.localeCompare(b.starts_at) ||
        a.appointment_id.localeCompare(b.appointment_id),
    )
}

export function appointmentDates(appointments: Appointment[]) {
  // Include an empty next day so the preview also demonstrates the empty state.
  const dates = [
    ...new Set(appointments.map((item) => dateInSingapore(item.starts_at))),
  ].sort()
  if (!dates.length) return [dateInSingapore(shared.as_of)]
  dates.push(
    new Date(Date.parse(dates[dates.length - 1]) + 86400000)
      .toISOString()
      .slice(0, 10),
  )
  return dates
}

export function dayCells(appointments: Appointment[], date: string) {
  const start = Date.parse(`${date}T00:00:00+08:00`)
  const day = appointments.filter(
    (item) => dateInSingapore(item.starts_at) === date,
  )
  // Normal display is 08:00–18:00; expand to include any earlier/later fixture.
  const first = Math.min(
    16,
    ...day.map((item) =>
      Math.floor((Date.parse(item.starts_at) - start) / 1800000),
    ),
  )
  const last = Math.max(
    36,
    ...day.map((item) =>
      Math.ceil((Date.parse(item.ends_at) - start) / 1800000),
    ),
  )
  return Array.from({ length: last - first }, (_, index) => {
    const begins = start + (first + index) * 1800000
    return {
      startsAt: new Date(begins).toISOString(),
      endsAt: new Date(begins + 1800000).toISOString(),
      appointments: day.filter(
        (item) =>
          Date.parse(item.starts_at) < begins + 1800000 &&
          Date.parse(item.ends_at) > begins,
      ),
    }
  })
}

export function subjectName(id: string) {
  return (
    shared.subjects.find((subject) => subject.subject_id === id)
      ?.display_name ?? id
  )
}

export function clinicName(id: string) {
  return shared.clinics.find((clinic) => clinic.tenant_id === id)?.name ?? id
}

export function readableStatus(value: string) {
  return value.replaceAll('_', ' ')
}

export function formatDate(date: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  }).format(new Date(`${date}T00:00:00+08:00`))
}

export function formatTime(instant: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(instant))
}
