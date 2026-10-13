export function consultationPrice(amountMinor: number, currency: string) {
  return new Intl.NumberFormat('en-SG', { style: 'currency', currency }).format(amountMinor / 100)
}
