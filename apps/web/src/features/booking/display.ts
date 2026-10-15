export function formatBookingDate(date: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(new Date(`${date}T00:00:00+08:00`))
}
export function formatBookingTime(instant: string) {
  return new Intl.DateTimeFormat('en-SG', {
    timeZone: 'Asia/Singapore',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(instant))
}
