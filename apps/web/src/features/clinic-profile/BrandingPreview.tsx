import { HeartPulse } from 'lucide-react'
import { consultationPrice } from '@/lib/money'
import { feeMinor } from './profile'
import type { ProfileDraft } from './profile'

export function BrandingPreview({ draft, logoPreview }: { draft: ProfileDraft; logoPreview: string | null }) {
  const color = /^#[0-9a-f]{6}$/i.test(draft.primaryColor) ? draft.primaryColor : '#64748b'
  const minor = feeMinor(draft.fee)

  return (
    <aside aria-labelledby="preview-heading" className="self-start lg:sticky lg:top-6">
      <h2 id="preview-heading" className="text-sm font-semibold">Branding preview</h2>
      <p className="mt-1 text-xs text-slate-500">Updates as you edit. Logo changes save immediately.</p>
      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="h-1.5" style={{ backgroundColor: color }} />
        <div className="p-6 sm:p-8">
          <div className="flex items-center gap-3">
            <span className="relative flex size-12 shrink-0 items-center justify-center overflow-hidden rounded-xl text-white" style={{ backgroundColor: color }} aria-hidden="true">
              <HeartPulse className="size-6" />
              {logoPreview && <img key={logoPreview} src={logoPreview} alt="" className="absolute inset-0 size-full bg-white object-contain" onError={event => { event.currentTarget.hidden = true }} />}
            </span>
            <h3 className="min-w-0 text-lg font-semibold break-words">{draft.name.trim() || 'Clinic name'}</h3>
          </div>
          <p className="mt-6 text-2xl font-semibold tracking-tight">Your clinic, wherever you are.</p>
          <p className="mt-3 text-sm leading-relaxed break-words whitespace-pre-wrap text-slate-600">{draft.description || 'Your clinic description will appear here.'}</p>
          <div className="mt-6 border-t border-slate-200 pt-5">
            <p className="text-xs text-slate-500">Consultation fee</p>
            <p className="mt-2 text-3xl font-semibold break-words">{minor === null ? 'Enter a valid amount' : `${consultationPrice(minor, 'SGD')} SGD`}</p>
          </div>
        </div>
      </div>
    </aside>
  )
}
