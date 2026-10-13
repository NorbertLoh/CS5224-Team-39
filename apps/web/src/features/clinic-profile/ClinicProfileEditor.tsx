import { useCallback, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readSession } from '@/auth/session'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { BrandingPreview } from './BrandingPreview'
import { ClinicProfileForm } from './ClinicProfileForm'
import { profileDraft, profileUpdate, validateProfile } from './profile'
import type { ClinicProfile, ProfileDraft, ProfileErrors } from './profile'
import { readClinic, saveClinic } from './logo-api'
import type { EditableClinic } from './logo-api'

export function ClinicProfileEditor({ tenantId }: { tenantId: string | undefined }) {
  const query = useQuery({
    queryKey: ['clinic-profile', readSession()?.accessToken, tenantId],
    queryFn: () => readClinic(tenantId!),
    enabled: Boolean(tenantId),
  })
  if (!tenantId) return <ErrorState message="Clinic address is invalid." />
  if (query.isPending) return <LoadingState message="Loading clinic profile..." />
  if (query.isError) return <main className="mx-auto max-w-xl px-6 py-16"><ErrorState message="Could not load this clinic. Sign in as its administrator and try again." onRetry={() => void query.refetch()} /><a href="/" className="mt-5 inline-block underline">Return home to sign in</a></main>
  return <ProfileEditor key={query.data.tenant_id} clinic={query.data} />
}

function ProfileEditor({ clinic }: { clinic: EditableClinic }) {
  const [saved, setSaved] = useState<ClinicProfile>(clinic)
  const savedRef = useRef<ClinicProfile>(clinic)
  const [draft, setDraft] = useState(() => profileDraft(clinic))
  const [errors, setErrors] = useState<ProfileErrors>({})
  const [message, setMessage] = useState('')
  const [logoPreview, setLogoPreview] = useState<string | null>(clinic.branding.logo_url)
  const [saving, setSaving] = useState(false)

  const changeLogo = useCallback((url: string | null, preview: string | null) => {
    const updated = { ...savedRef.current, branding: { ...savedRef.current.branding, logo_url: url } }
    savedRef.current = updated
    setDraft(current => ({ ...current, logoUrl: url ?? '' }))
    setSaved(updated)
    setLogoPreview(preview)
  }, [])

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
      const updated = await saveClinic(clinic.tenant_id, profileUpdate(draft))
      savedRef.current = updated
      setSaved(updated)
      setDraft(profileDraft(updated))
      setMessage('Clinic profile saved.')
    } catch { setMessage('Could not save the profile. Your edits are still here; try again.') }
    finally { setSaving(false) }
  }

  function reset() {
    setDraft(profileDraft(saved))
    setErrors({})
    setMessage('Unsaved changes discarded.')
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-5 sm:px-8"><a href="/" className="font-semibold">TeleLink Health</a><span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-600">Clinic administration</span></div></header>
      <main className="mx-auto max-w-6xl px-6 py-10 sm:px-8">
        {<a href={`/clinics/${clinic.slug}`} className="text-sm text-slate-600 underline underline-offset-4">View storefront</a>}
        <h1 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">Clinic profile & branding</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-slate-600">{`Edit ${saved.name}'s profile. Logo changes save immediately; use Save changes for the remaining fields.`}</p>
        <p className="mt-3 text-xs text-slate-500">Storefront address: /clinics/{clinic.slug} · The address cannot be changed here.</p>
        <div className="mt-5 grid items-start gap-8 lg:grid-cols-[1.4fr_1fr]">
          <ClinicProfileForm draft={draft} errors={errors} onChange={change} onSave={save} onReset={reset} tenantId={clinic.tenant_id} logoPreview={logoPreview} onLogoChange={changeLogo} saving={saving} message={message} />
          <BrandingPreview draft={draft} logoPreview={logoPreview} />
        </div>
      </main>
    </div>
  )
}
