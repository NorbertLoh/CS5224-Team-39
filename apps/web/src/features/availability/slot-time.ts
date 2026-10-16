export function slotStart(date: string, time: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time))
    return NaN
  const value = Date.parse(`${date}T${time}:00+08:00`)
  // Reject calendar rollovers as well as malformed input.
  if (
    !Number.isFinite(value) ||
    new Date(value + 8 * 3600000).toISOString().slice(0, 16) !==
      `${date}T${time}`
  )
    return NaN
  return value
}
