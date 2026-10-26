import type { Doctor } from '@/features/clinics/api'
import { Stethoscope } from 'lucide-react'

export function DoctorList({ doctors }: { doctors: Doctor[] }) {
  return (
    <section
      id="doctors"
      aria-labelledby="doctors-heading"
      className="scroll-mt-6 border-t border-slate-200 pt-10"
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-slate-500 uppercase">
            People behind your care
          </p>
          <h2
            id="doctors-heading"
            className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl"
          >
            Meet our doctors
          </h2>
        </div>
        <p className="text-sm text-slate-500">
          {doctors.length} {doctors.length === 1 ? 'doctor' : 'doctors'} at this
          clinic
        </p>
      </div>
      {doctors.length ? (
        <ul className="mt-6 grid gap-4 sm:grid-cols-2">
          {doctors.map((doctor) => (
            <li
              key={doctor.doctor_id}
              className="flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-6"
            >
              <span
                className="flex size-12 shrink-0 items-center justify-center rounded-full bg-slate-100 text-[var(--clinic-color)]"
                aria-hidden="true"
              >
                <Stethoscope className="size-5" />
              </span>
              <div>
                <h3 className="font-semibold">{doctor.display_name}</h3>
                <p className="mt-1 text-sm text-slate-500">Clinic doctor</p>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-6 text-slate-600">
          No doctors are listed at this clinic yet.
        </p>
      )}
    </section>
  )
}
