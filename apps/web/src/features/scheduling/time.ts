export function singaporeDate(now = Date.now()) {
  return new Date(now + 8 * 3600000).toISOString().slice(0, 10)
}
export function shiftDate(date: string, days: number) {
  return new Date(Date.parse(date) + days * 86400000).toISOString().slice(0, 10)
}
export function dayStart(date: string) {
  return new Date(`${date}T00:00:00+08:00`).toISOString()
}
