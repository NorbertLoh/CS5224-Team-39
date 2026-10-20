import type { Appointment } from '../scheduling/api'

export function dateInSingapore(instant: string) {
  return new Date(Date.parse(instant) + 8 * 3600000).toISOString().slice(0, 10)
}

export function dayCells(appointments: Appointment[], date: string) {
  const start = Date.parse(`${date}T00:00:00+08:00`)
  const day = appointments.filter(
    (item) => dateInSingapore(item.starts_at) === date,
  )
  // Normal display is 08:00–18:00; expand to include any earlier/later appointment.
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

// Names are booking-time snapshots; older appointments only have identifiers.
export function nameOrId(name: string | null | undefined, id: string) {
  return name || id
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
