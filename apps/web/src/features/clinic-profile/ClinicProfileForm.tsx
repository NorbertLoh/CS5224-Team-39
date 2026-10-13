import type { FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { ProfileField } from './ProfileField'
import type { ProfileDraft, ProfileErrors } from './profile'
import { LogoUpload } from './LogoUpload'
import { profileApiEnabled } from './logo-api'

const inputClass = 'w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-700 aria-invalid:border-red-600'

export function ClinicProfileForm({ draft, errors, onChange, onSave, onReset, tenantId, logoPreview, onLogoChange, saving }: {
  draft: ProfileDraft
  errors: ProfileErrors
  onChange: (field: keyof ProfileDraft, value: string) => void
  onSave: (event: FormEvent<HTMLFormElement>) => void
  onReset: () => void
  tenantId: string
  logoPreview: string | null
  onLogoChange: (url: string | null, preview: string | null) => void
  saving: boolean
}) {
  function fieldProps(field: keyof ProfileDraft) {
    return {
      id: `profile-${field}`,
      name: field,
      value: draft[field],
      'aria-invalid': !!errors[field],
      'aria-describedby': errors[field] ? `profile-${field}-error` : undefined,
      onChange: (event: { target: { value: string } }) => onChange(field, event.target.value),
      className: inputClass,
    }
  }

  return (
    <form noValidate onSubmit={onSave} className="rounded-2xl border border-slate-200 bg-white">
      <fieldset disabled={saving} className="space-y-5 border-b border-slate-200 p-6 sm:p-8">
        <legend className="float-left mb-5 w-full text-lg font-semibold">Clinic details</legend>
        <ProfileField name="name" label="Clinic name" error={errors.name}>
          <input {...fieldProps('name')} required maxLength={200} autoComplete="organization" />
        </ProfileField>
        <ProfileField name="description" label="Description" hint="Introduce your clinic in plain text." error={errors.description}>
          <textarea {...fieldProps('description')} rows={4} maxLength={2000} />
        </ProfileField>
      </fieldset>
      <fieldset disabled={saving} className="space-y-5 border-b border-slate-200 p-6 sm:p-8">
        <legend className="float-left mb-5 w-full text-lg font-semibold">Branding</legend>
        <ProfileField name="primaryColor" label="Primary colour" hint="A six-digit hex colour for your clinic's accents." error={errors.primaryColor}>
          <div className="flex gap-3">
            <input type="color" aria-label="Choose primary colour" value={/^#[0-9a-f]{6}$/i.test(draft.primaryColor) ? draft.primaryColor : '#156B63'} onChange={event => onChange('primaryColor', event.target.value)} className="h-11 w-12 shrink-0 cursor-pointer rounded-lg border border-slate-300 bg-white p-1" />
          <input {...fieldProps('primaryColor')} required maxLength={7} spellCheck={false} />
          </div>
        </ProfileField>
        <ProfileField name="logoUrl" label="Clinic logo (optional)" error={errors.logoUrl}>
          <LogoUpload tenantId={tenantId} preview={logoPreview} onChange={onLogoChange} />
        </ProfileField>
      </fieldset>
      <fieldset disabled={saving} className="space-y-5 p-6 sm:p-8">
        <legend className="float-left mb-5 w-full text-lg font-semibold">Consultation fee</legend>
        <ProfileField name="fee" label="Amount in SGD" hint="Enter dollars and cents; for example, 25.50." error={errors.fee}>
          <input {...fieldProps('fee')} required inputMode="decimal" maxLength={20} />
        </ProfileField>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-200 px-6 py-5 sm:px-8">
        <Button type="submit" disabled={saving} className="h-10 px-5">{saving ? 'Saving…' : profileApiEnabled ? 'Save changes' : 'Save demo changes'}</Button>
        <Button type="button" disabled={saving} variant="outline" className="h-10 px-5" onClick={onReset}>Discard unsaved changes</Button>
      </div>
    </form>
  )
}
