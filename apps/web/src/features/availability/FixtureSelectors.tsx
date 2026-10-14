import { fixtureClinics, fixtureDoctors } from './fixtures'

const fieldClass = 'mt-2 w-full rounded-lg border bg-white px-3 py-2 text-base'

type FixtureSelectorsProps = {
  tenantId: string
  doctorId: string
  onClinicChange: (tenantId: string) => void
  onDoctorChange: (doctorId: string) => void
}

export function FixtureSelectors({
  tenantId,
  doctorId,
  onClinicChange,
  onDoctorChange,
}: FixtureSelectorsProps) {
  return (
    <div className="space-y-5">
      <aside className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
        <strong>Fixture preview</strong>
        <p className="mt-1">
          Choose a demo clinic and doctor to try the editor. Changes last until
          you reload this page and do not change real availability.
        </p>
      </aside>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm font-medium">
          Demo clinic
          <select
            className={fieldClass}
            value={tenantId}
            onChange={(event) => onClinicChange(event.target.value)}
          >
            {fixtureClinics.map((clinic) => (
              <option key={clinic.tenant_id} value={clinic.tenant_id}>
                {clinic.name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm font-medium">
          Demo doctor
          <select
            className={fieldClass}
            value={doctorId}
            onChange={(event) => onDoctorChange(event.target.value)}
          >
            {fixtureDoctors(tenantId).map((doctor) => (
              <option key={doctor.subject_id} value={doctor.subject_id}>
                {doctor.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  )
}
