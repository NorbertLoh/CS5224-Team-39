import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { useClinicPrescriptions } from '@/features/fulfilment/pricing/clinicMedicineQueries'
import { PrescriptionPriceCard } from '@/features/fulfilment/pricing/PrescriptionPriceCard'

export function ClinicMedicinePricing({
  tenantId,
  token,
}: {
  tenantId: string
  token: string
}) {
  const prescriptions = useClinicPrescriptions(tenantId, token)
  const rows = prescriptions.data?.filter((row) => row.items.length > 0) ?? []
  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6">
      <div>
        <h1 className="text-3xl font-semibold">Medicine Pricing</h1>
        <p className="mt-1 text-sm text-slate-600">
          Set medicine prices for issued prescriptions.
        </p>
      </div>
      {prescriptions.isPending ? (
        <LoadingState message="Loading medicine prescriptions..." />
      ) : prescriptions.isError ? (
        <ErrorState
          message="Could not load prescriptions. Check your clinic access and retry."
          onRetry={() => void prescriptions.refetch()}
        />
      ) : rows.length ? (
        rows.map((prescription) => (
          <PrescriptionPriceCard
            key={prescription.prescription_id}
            prescription={prescription}
            tenantId={tenantId}
            token={token}
          />
        ))
      ) : (
        <p className="text-sm text-slate-600">
          Issued medicine prescriptions will appear here.
        </p>
      )}
    </main>
  )
}
