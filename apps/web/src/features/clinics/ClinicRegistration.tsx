import { useState } from 'react'
import type { FormEvent } from 'react'
import { ApiError } from '../../lib/api'
import { clinicRequest } from './api'
import type { Clinic } from './api'
import { profileUpdate, validateProfile } from '../clinic-profile/profile'
import type { ProfileDraft } from '../clinic-profile/profile'

export function ClinicRegistration() {
  const [slug, setSlug] = useState('')
  const [draft, setDraft] = useState<ProfileDraft>({
    name: '',
    description: '',
    primaryColor: '#156B63',
    logoUrl: '',
    fee: '',
  })
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const errors = Object.values(validateProfile(draft))
    if (!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) || slug.length > 100)
      errors.unshift('Use lowercase letters, numbers and single hyphens for the clinic address.')
    if (errors.length) {
      setMessage(errors.join(' '))
      return
    }
    setBusy(true)
    setMessage('')
    try {
      const response = await clinicRequest(
        '/clinics',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ slug, ...profileUpdate(draft) }),
        },
        true,
      )
      const clinic: Clinic = await response.json()
      window.location.assign(
        `/clinic-admin/clinics/${encodeURIComponent(clinic.tenant_id)}/profile`,
      )
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 409
          ? 'This clinic address is already registered. Choose another address, or open your existing clinic from Manage clinic.'
          : 'Could not register the clinic. Your details are still here. Retry with the same details to resume the application.',
      )
      setBusy(false)
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-3xl font-semibold">Register your clinic</h1>
      <p className="mt-3 text-slate-600">You will become this clinic’s administrator. Your application needs platform approval before patients can find and book the clinic. Add existing doctor and administrator accounts under Manage clinic → Staff.</p>
      <form onSubmit={(event) => void submit(event)} className="mt-6 space-y-5">
        <fieldset disabled={busy} className="space-y-5">
          <label className="flex flex-col gap-2">Clinic name
            <input required maxLength={200} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} className="rounded border p-3" />
          </label>
          <label className="flex flex-col gap-2">Clinic address name
            <input required maxLength={100} pattern="[a-z0-9]+(-[a-z0-9]+)*" value={slug} onChange={(event) => setSlug(event.target.value)} aria-describedby="clinic-address-help" className="rounded border p-3" />
          </label>
          <p id="clinic-address-help" className="text-sm text-slate-600">Your storefront will be /clinics/{slug || 'your-clinic'}. Use lowercase letters, numbers and hyphens. This address cannot be changed later.</p>
          <label className="flex flex-col gap-2">Consultation price (SGD)
            <input required inputMode="decimal" value={draft.fee} onChange={(event) => setDraft({ ...draft, fee: event.target.value })} className="rounded border p-3" />
          </label>
          <label className="flex flex-col gap-2">Description
            <textarea maxLength={2000} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} className="rounded border p-3" />
          </label>
          <label className="flex flex-col gap-2">Brand colour
            <input type="color" value={draft.primaryColor} onChange={(event) => setDraft({ ...draft, primaryColor: event.target.value })} />
          </label>
          <p role="status" aria-live="polite" className="text-sm">{message}</p>
          <button type="submit" className="rounded-md bg-slate-900 px-4 py-3 font-medium text-white disabled:opacity-60">{busy ? 'Submitting…' : 'Submit clinic application'}</button>
        </fieldset>
      </form>
    </main>
  )
}
