import { useState } from 'react'
import type { FormEvent } from 'react'
import fixtures from '../storefront/fixtures.json'
import { BrandingPreview } from './BrandingPreview'
import { ClinicProfileForm } from './ClinicProfileForm'
import { profileDraft, profileUpdate, validateProfile } from './profile'
import type { ClinicProfile, ProfileDraft, ProfileErrors } from './profile'

export function ClinicProfileEditor({ slug }: { slug: string | undefined }) {
  const clinic = fixtures.find(item => item.slug === slug)
  if (!clinic) {
    return <main className="mx-auto max-w-xl px-6 py-24"><h1 className="text-3xl font-semibold">Clinic unavailable</h1><p className="mt-3 text-slate-600">This clinic was not found in the demo.</p><a href="/" className="mt-6 inline-block underline underline-offset-4">Return to demo clinics</a></main>
  }
  return <ProfileEditor key={clinic.tenant_id} clinic={clinic} />
}

function ProfileEditor({ clinic }: { clinic: ClinicProfile & { slug: string } }) {
  const [saved, setSaved] = useState<ClinicProfile>(clinic)
  const [draft, setDraft] = useState(() => profileDraft(clinic))
  const [errors, setErrors] = useState<ProfileErrors>({})
  const [message, setMessage] = useState('')

  function change(field: keyof ProfileDraft, value: string) {
    setDraft(current => ({ ...current, [field]: value }))
    setErrors(current => ({ ...current, [field]: undefined }))
    setMessage('')
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validateProfile(draft)
    setErrors(nextErrors)
    const firstError = Object.keys(nextErrors)[0]
    if (firstError) {
      setMessage('Please correct the highlighted fields.')
      document.getElementById(`profile-${firstError}`)?.focus()
      return
    }
    const updated = profileUpdate(draft)
    setSaved(updated)
    setDraft(profileDraft(updated))
    setMessage('Demo changes saved in this editor. Nothing was published.')
  }

  function reset() {
    setDraft(profileDraft(saved))
    setErrors({})
    setMessage('Unsaved changes discarded.')
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-5 sm:px-8"><a href="/" className="font-semibold">TeleLink Health</a><span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600">Clinic administrator demo</span></div></header>
      <main className="mx-auto max-w-6xl px-6 py-10 sm:px-8">
        <a href={`/clinics/${clinic.slug}`} className="text-sm text-slate-600 underline underline-offset-4">View original demo storefront</a>
        <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Clinic profile & branding</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">Edit {clinic.name}'s profile using sample data. Saved changes stay in this editor and reset when you leave or reload. Live clinic access and publishing are not connected yet.</p>
        <p className="mt-3 text-xs text-slate-500">Storefront address: /clinics/{clinic.slug} · The address cannot be changed here.</p>
        <div role="status" aria-live="polite" className="mt-5 min-h-6 text-sm font-medium">{message}</div>
        <div className="mt-5 grid items-start gap-8 lg:grid-cols-[1.4fr_1fr]">
          <ClinicProfileForm draft={draft} errors={errors} onChange={change} onSave={save} onReset={reset} />
          <BrandingPreview draft={draft} />
        </div>
      </main>
    </div>
  )
}
