import { Stethoscope } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { consultationPrice } from '@/lib/money'
import type { Clinic } from '../clinics/api'

export function ConsultationCard({ price, slug, active }: { price: Clinic['consultation_price']; slug: string; active: boolean }) {
  return (
    <aside aria-labelledby="consultation-heading" className="self-start overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-3 border-b border-slate-100 p-6 sm:p-8">
        <span className="rounded-xl bg-slate-100 p-3"><Stethoscope className="size-6 text-[var(--clinic-color)]" aria-hidden="true" /></span>
        <div><p className="text-xs text-slate-500">Consultation</p><h2 id="consultation-heading" className="mt-1 font-semibold">A conversation about your health</h2></div>
      </div>
      <div className="p-6 sm:p-8">
        <p className="text-sm text-slate-500">Clinic consultation fee</p>
        <p className="mt-2 text-4xl font-semibold tracking-tight">{consultationPrice(price.amount_minor, price.currency)} <span className="text-sm font-normal text-slate-500">SGD</span></p>
        <p className="mt-4 text-sm leading-relaxed text-slate-600">Get to know the clinic's doctors below before choosing your consultation.</p>
        {active ? <Button asChild className="mt-6 h-11 w-full"><a href={`/patient/clinics/${encodeURIComponent(slug)}/book`}>Book a consultation</a></Button> : <Button disabled className="mt-6 h-11 w-full">Booking unavailable</Button>}
        <p className="mt-3 text-xs leading-relaxed text-slate-500">{active ? 'Choose a date and a 30-minute time slot. Reserve your time and continue to secure payment.' : 'This clinic is not accepting bookings.'}</p>
      </div>
    </aside>
  )
}
