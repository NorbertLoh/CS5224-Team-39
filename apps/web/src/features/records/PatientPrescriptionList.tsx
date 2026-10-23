import { useEffect, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { listPrescriptions, recordsError } from './api'
import { PrescriptionSummary } from './PrescriptionSummary'
import { PatientPrescriptionDetail } from './PatientPrescriptionDetail'
import { PatientMedicationCard } from './PatientMedicationCard'
import { patientMedicationOrders } from '../fulfilment/patientMedicines'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function PatientPrescriptionList({
  token,
  subjectId,
  headingLevel = 2,
}: {
  token: string
  subjectId: string
  headingLevel?: 1 | 2
}) {
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  const [selected, setSelected] = useState<string | null>(null)
  const query = useInfiniteQuery({
    queryKey: ['records', 'patient', token],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listPrescriptions(undefined, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    refetchInterval: 15000,
  })
  const { hasNextPage, isFetching, isError, fetchNextPage } = query
  useEffect(() => {
    if (hasNextPage && !isFetching && !isError) void fetchNextPage()
  }, [hasNextPage, isFetching, isError, fetchNextPage])
  const prescriptions =
    query.data?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.patient_id === subjectId)
      .sort(
        (a, b) =>
          Date.parse(b.issued_at ?? b.created_at) -
          Date.parse(a.issued_at ?? a.created_at),
      ) ?? []
  const orders = useQuery({
    queryKey: ['fulfilment', 'patient-medicines', token, subjectId],
    queryFn: ({ signal }) => patientMedicationOrders(subjectId, signal),
    enabled: prescriptions.some(
      (item) => item.status === 'issued' && item.items.length > 0,
    ),
    retry: false,
    gcTime: 0,
    refetchInterval: 15000,
  })
  return (
    <section
      className="mt-6 space-y-4 rounded-xl border bg-white p-5 sm:p-6"
      aria-labelledby="prescription-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Heading
            id="prescription-heading"
            className={
              headingLevel === 1
                ? 'text-3xl font-semibold'
                : 'text-xl font-semibold'
            }
          >
            Prescriptions & medicines
          </Heading>
          <p className="mt-1 text-sm text-slate-600">
            Your medicines and instructions. Medication and delivery are paid
            separately from consultations.
          </p>
        </div>
        <button
          className="rounded border px-4 py-2 text-sm"
          disabled={query.isFetching}
          onClick={() => {
            setSelected(null)
            void query.refetch()
            if (orders.isEnabled) void orders.refetch()
          }}
        >
          Refresh prescriptions
        </button>
      </div>
      {query.isPending ? (
        <LoadingState message="Loading prescriptions..." />
      ) : query.isError ? (
        <ErrorState
          message={recordsError(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          {!prescriptions.length && (
            <p role="status">No prescriptions available.</p>
          )}
          <ul className="divide-y">
            {prescriptions.map((prescription) => (
              <li key={prescription.prescription_id}>
                <PrescriptionSummary
                  prescription={prescription}
                  token={token}
                  selected={selected === prescription.prescription_id}
                  onToggle={() =>
                    setSelected((current) =>
                      current === prescription.prescription_id
                        ? null
                        : prescription.prescription_id,
                    )
                  }
                >
                  <PatientMedicationCard
                    prescription={prescription}
                    order={orders.data?.find(
                      (order) =>
                        order.prescription_id ===
                          prescription.prescription_id &&
                        order.tenant_id === prescription.tenant_id &&
                        order.appointment_id === prescription.appointment_id,
                    )}
                    checking={orders.isPending}
                    unavailable={orders.isError}
                  >
                    {selected === prescription.prescription_id && (
                      <PatientPrescriptionDetail
                        key={selected}
                        id={selected}
                        token={token}
                        subjectId={subjectId}
                      />
                    )}
                  </PatientMedicationCard>
                </PrescriptionSummary>
              </li>
            ))}
          </ul>
          {query.hasNextPage && (
            <button
              className="rounded border px-4 py-2"
              disabled={query.isFetchingNextPage}
              onClick={() => void query.fetchNextPage()}
            >
              Load more prescriptions
            </button>
          )}
        </>
      )}
    </section>
  )
}
