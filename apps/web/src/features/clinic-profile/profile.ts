import type { Money } from '@/lib/api-types'

export type ClinicProfile = {
  name: string
  branding: { primary_color: string; logo_url: string | null; description: string }
  consultation_price: Money
}

export type ProfileDraft = {
  name: string
  description: string
  primaryColor: string
  logoUrl: string
  fee: string
}

export type ProfileErrors = Partial<Record<keyof ProfileDraft, string>>

export function profileDraft(profile: ClinicProfile): ProfileDraft {
  const minor = profile.consultation_price.amount_minor
  return {
    name: profile.name,
    description: profile.branding.description,
    primaryColor: profile.branding.primary_color,
    logoUrl: profile.branding.logo_url ?? '',
    fee: `${Math.floor(minor / 100)}.${String(minor % 100).padStart(2, '0')}`,
  }
}

export function feeMinor(value: string): number | null {
  if (value.length > 20 || !/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null
  const [whole, fraction = ''] = value.trim().split('.')
  const minor = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, '0'))
  return minor <= BigInt(Number.MAX_SAFE_INTEGER) ? Number(minor) : null
}

export function validLogoUrl(value: string): boolean {
  if (value.length > 2048 || /\s/.test(value) || !/^https:\/\//i.test(value)) return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !!url.hostname && !url.username && !url.password
  } catch {
    return false
  }
}

export function validateProfile(draft: ProfileDraft): ProfileErrors {
  const errors: ProfileErrors = {}
  if (!draft.name.trim() || draft.name.length > 200) errors.name = 'Enter a clinic name of 1–200 characters.'
  if (draft.description.length > 2000 || /[<>]/.test(draft.description)) errors.description = 'Use plain text, up to 2,000 characters, without < or >.'
  if (!/^#[0-9a-f]{6}$/i.test(draft.primaryColor)) errors.primaryColor = 'Use a six-digit hex colour, such as #156B63.'
  if (draft.logoUrl && !validLogoUrl(draft.logoUrl)) errors.logoUrl = 'Use an HTTPS URL without spaces or embedded login details, or leave blank.'
  if (feeMinor(draft.fee) === null) errors.fee = 'Enter a nonnegative SGD amount with at most two decimal places, within the supported range.'
  return errors
}

// Call only after validation; this is the tenant PATCH writable shape.
export function profileUpdate(draft: ProfileDraft): ClinicProfile {
  return {
    name: draft.name.trim(),
    branding: {
      primary_color: draft.primaryColor,
      logo_url: draft.logoUrl || null,
      description: draft.description,
    },
    consultation_price: { amount_minor: feeMinor(draft.fee)!, currency: 'SGD' },
  }
}
