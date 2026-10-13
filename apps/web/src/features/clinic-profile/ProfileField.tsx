import type { ReactNode } from 'react'
import type { ProfileDraft } from './profile'

export function ProfileField({ name, label, hint, error, children }: {
  name: keyof ProfileDraft
  label: string
  hint?: string
  error?: string
  children: ReactNode
}) {
  return (
    <div>
      <label htmlFor={`profile-${name}`} className="block text-sm font-medium">{label}</label>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
      <div className="mt-2">{children}</div>
      {error && <p id={`profile-${name}-error`} className="mt-2 text-sm text-red-700">{error}</p>}
    </div>
  )
}
