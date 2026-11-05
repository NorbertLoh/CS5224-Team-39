import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { appointmentPrescriptions, recordsError } from '@/features/records/api'
import type { Appointment } from '@/features/scheduling/api'
import { useQuery } from '@tanstack/react-query'

export function PreviousVisitPrescriptions({
  visit,
  token,
  historyFor,
}: {
  visit: Appointment
  token: string
  historyFor: string
}) {
  const prescriptions = useQuery({
    queryKey: [
      'records',
      'previous-prescriptions',
      token,
      visit.appointment_id,
      historyFor,
    ],
    queryFn: async ({ signal }) => {
      const saved = await appointmentPrescriptions(
        visit.appointment_id,
        signal,
        historyFor,
      )
      if (
        saved.some(
          (prescription) =>
            !['issued', 'voided'].includes(prescription.status) ||
            (
              [
                'appointment_id',
                'tenant_id',
                'patient_id',
                'doctor_id',
              ] as const
            ).some((field) => prescription[field] !== visit[field]),
        )
      )
        throw new Error('Invalid previous prescription context')
      return saved
    },
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  return (
    <section
      aria-label="Previous visit prescriptions"
      className="mt-5 border-t border-slate-200 pt-4"
    >
      <h4 className="font-semibold text-slate-900">Prescriptions</h4>
      {prescriptions.isPending ? (
        <LoadingState message="Loading previous prescriptions..." />
      ) : prescriptions.isError ? (
        <ErrorState
          message={recordsError(prescriptions.error)}
          onRetry={() => void prescriptions.refetch()}
        />
      ) : !prescriptions.data.length ? (
        <p className="mt-2 text-sm text-slate-600">
          No issued prescriptions for this visit.
        </p>
      ) : (
        <div className="mt-3 space-y-3">
          {prescriptions.data.map((prescription) => (
            <div
              key={prescription.prescription_id}
              className="rounded-lg border border-slate-200 p-3"
            >
              <p className="text-sm font-medium">
                {prescription.status === 'voided'
                  ? 'Voided prescription'
                  : 'Issued prescription'}
              </p>
              {prescription.status === 'voided' && (
                <p className="mt-1 text-xs text-red-700">
                  This prescription is no longer valid.
                </p>
              )}
              {prescription.items.length ? (
                <ul className="mt-2 space-y-3">
                  {prescription.items.map((item) => (
                    <li
                      key={item.prescription_item_id}
                      className="break-words text-sm"
                    >
                      <p className="font-medium text-slate-800">
                        {item.display_name}
                      </p>
                      <p className="mt-1 text-slate-600">
                        Quantity: {item.quantity}
                      </p>
                      <p className="mt-1 whitespace-pre-wrap text-slate-700">
                        {item.instructions}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-2 text-sm text-slate-600">
                  No medicines prescribed.
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
