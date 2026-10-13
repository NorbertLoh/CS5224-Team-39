import fixtures from './fixtures.json'

export type StorefrontClinic = (typeof fixtures)[number]

export const storefrontClinics = fixtures.filter(clinic => clinic.status === 'active')

export function findClinic(slug: string | undefined, clinics = fixtures) {
  return clinics.find(clinic => clinic.slug === slug && clinic.status === 'active')
}

export function consultationPrice(amountMinor: number, currency: string) {
  return new Intl.NumberFormat('en-SG', { style: 'currency', currency }).format(amountMinor / 100)
}
