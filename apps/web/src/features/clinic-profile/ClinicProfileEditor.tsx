import { useCallback, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readSession } from '@/auth/session'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import fixtures from '../storefront/fixtures.json'
import { BrandingPreview } from './BrandingPreview'
import { ClinicProfileForm } from './ClinicProfileForm'
import { profileDraft, profileUpdate, validateProfile } from './profile'
import type { ClinicProfile, ProfileDraft, ProfileErrors } from './profile'
import { profileApiEnabled, readClinic, saveClinic } from './logo-api'
import type { EditableClinic } from './logo-api'
import { readDemoProfile, saveDemoProfile } from './demo-storage'

export function ClinicProfileEditor({ slug }: { slug: string | undefined }) {
  const clinic = fixtures.find(item => item.slug === slug)
  if (profileApiEnabled && slug) return <LiveProfileEditor tenantId={clinic?.tenant_id ?? slug} />
  if (!clinic) {
    return <main className="mx-auto max-w-xl px-6 py-24"><h1 className="text-3xl font-semibold">Clinic unavailable</h1><p className="mt-3 text-slate-600">This clinic was not found in the demo.</p><a href="/" className="mt-6 inline-block underline underline-offset-4">Return to demo clinics</a></main>
  }
  return <ProfileEditor key={clinic.tenant_id} clinic={clinic} />
}

function LiveProfileEditor({ tenantId }: { tenantId: string }) {
  const query = useQuery({
    queryKey: ['clinic-profile', readSession()?.accessToken, tenantId],
    queryFn: () => readClinic(tenantId),
  })
  if (query.isPending) return <LoadingState message="Loading clinic profile…" />
  if (query.isError) return <main className="mx-auto max-w-xl px-6 py-16"><ErrorState message="Could not load this clinic. Sign in as its administrator and try again." onRetry={() => void query.refetch()} /><a href="/" className="mt-5 inline-block underline">Return home to sign in</a></main>
  return <ProfileEditor key={query.data.tenant_id} clinic={query.data} />
}

function ProfileEditor({ clinic }: { clinic: EditableClinic }) {
  const [initial] = useState(() => profileApiEnabled
    ? { profile: clinic, logoPreview: clinic.branding.logo_url }
    : readDemoProfile(clinic.tenant_id, clinic))
  const [saved, setSaved] = useState<ClinicProfile>(initial.profile)
  const savedRef = useRef(initial.profile)
  const [draft, setDraft] = useState(() => profileDraft(initial.profile))
  const [errors, setErrors] = useState<ProfileErrors>({})
  const [message, setMessage] = useState('')
  const [logoPreview, setLogoPreview] = useState<string | null>(initial.logoPreview)
  const [saving, setSaving] = useState(false)

  const changeLogo = useCallback((url: string | null, preview: string | null) => {
    const updated = { ...savedRef.current, branding: { ...savedRef.current.branding, logo_url: url } }
    if (!profileApiEnabled) saveDemoProfile(clinic.tenant_id, updated, preview)
    savedRef.current = updated
    setDraft(current => ({ ...current, logoUrl: url ?? '' }))
    setSaved(updated)
    setLogoPreview(preview)
  }, [clinic.tenant_id])

  function change(field: keyof ProfileDraft, value: string) {
    setDraft(current => ({ ...current, [field]: value }))
    setErrors(current => ({ ...current, [field]: undefined }))
    setMessage('')
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const nextErrors = validateProfile(draft)
    setErrors(nextErrors)
    const firstError = Object.keys(nextErrors)[0]
    if (firstError) {
      setMessage('Please correct the highlighted fields.')
      document.getElementById(`profile-${firstError}`)?.focus()
      return
    }
    setSaving(true)
    try {
      const updated = profileApiEnabled ? await saveClinic(clinic.tenant_id, profileUpdate(draft)) : profileUpdate(draft)
      if (!profileApiEnabled) saveDemoProfile(clinic.tenant_id, updated, logoPreview)
      savedRef.current = updated
      setSaved(updated)
      setDraft(profileDraft(updated))
      setMessage(profileApiEnabled ? 'Clinic profile saved.' : 'Demo profile saved in this browser.')
    } catch { setMessage(profileApiEnabled ? 'Could not save the profile. Your edits are still here; try again.' : 'Could not save in this browser. Storage may be full or disabled; your edits are still here.') }
    finally { setSaving(false) }
  }

  function reset() {
    setDraft(profileDraft(saved))
    setErrors({})
    setMessage('Unsaved changes discarded.')
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-5 sm:px-8"><a href="/" className="font-semibold">TeleLink Health</a><span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600">{profileApiEnabled ? 'Clinic administration' : 'Clinic administrator demo'}</span></div></header>
      <main className="mx-auto max-w-6xl px-6 py-10 sm:px-8">
        {!profileApiEnabled && <a href={`/clinics/${clinic.slug}`} className="text-sm text-slate-600 underline underline-offset-4">View original demo storefront</a>}
        <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Clinic profile & branding</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">{profileApiEnabled ? `Edit ${saved.name}'s profile. Logo changes save immediately; use Save changes for the remaining fields.` : `Edit ${saved.name}'s demo profile. Saves stay in this browser, including after reload. Logo changes save immediately; nothing is published to the live clinic.`}</p>
        <p className="mt-3 text-xs text-slate-500">Storefront address: /clinics/{clinic.slug} · The address cannot be changed here.</p>
        <div className="mt-5 grid items-start gap-8 lg:grid-cols-[1.4fr_1fr]">
          <ClinicProfileForm draft={draft} errors={errors} onChange={change} onSave={save} onReset={reset} tenantId={clinic.tenant_id} logoPreview={logoPreview} onLogoChange={changeLogo} saving={saving} message={message} />
          <BrandingPreview draft={draft} logoPreview={logoPreview} />
        </div>
      </main>
    </div>
  )
}
