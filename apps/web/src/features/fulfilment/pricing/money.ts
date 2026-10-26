export function minorUnits(value: string): number | null {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
  if (!match) return null
  const amount =
    Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'))
  return Number.isSafeInteger(amount) && amount >= 0 ? amount : null
}

export function decimal(minor: number) {
  return `${Math.trunc(minor / 100)}.${String(minor % 100).padStart(2, '0')}`
}
