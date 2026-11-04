import { ClinicList } from '@/features/platform-clinics/ClinicList'
import { ClinicManagement } from '@/features/platform-clinics/ClinicManagement'

export function PlatformClinics({
  token,
  tenantId,
}: {
  token: string
  tenantId?: string
}) {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      {tenantId && (
        <a
          href="/platform-admin/clinics"
          className="mb-6 inline-block text-sm underline"
        >
          Back to clinics
        </a>
      )}
      <h1 className="text-3xl font-semibold">
        {tenantId ? 'Manage clinic' : 'Platform clinics'}
      </h1>
      <p className="mt-3 text-slate-600">
        {tenantId
          ? 'Review this clinic and set its platform commission rate.'
          : 'Select a clinic to review its application and manage commission.'}
      </p>
      {tenantId ? (
        <ClinicManagement token={token} tenantId={tenantId} />
      ) : (
        <ClinicList token={token} />
      )}
    </main>
  )
}
