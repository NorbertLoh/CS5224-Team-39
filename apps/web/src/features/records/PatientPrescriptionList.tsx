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
}: {
  token: string
  subjectId: string
}) {
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
      className="mt-8 space-y-4 rounded-xl border p-6"
      aria-labelledby="prescription-heading"
    >
      <h2 id="prescription-heading" className="text-xl font-semibold">
        Prescriptions & medicines
      </h2>
      <button
        className="rounded border px-4 py-2"
        disabled={query.isFetching}
        onClick={() => {
          setSelected(null)
          void query.refetch()
          if (orders.isEnabled) void orders.refetch()
        }}
      >
        Refresh prescriptions
      </button>
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
          {prescriptions.map((prescription) => (
            <PatientMedicationCard
              key={prescription.prescription_id}
              prescription={prescription}
              order={orders.data?.find(
                (order) =>
                  order.prescription_id === prescription.prescription_id &&
                  order.tenant_id === prescription.tenant_id &&
                  order.appointment_id === prescription.appointment_id,
              )}
              checking={orders.isPending}
              unavailable={orders.isError}
            >
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
              />
              {selected === prescription.prescription_id && (
                <PatientPrescriptionDetail
                  key={selected}
                  id={selected}
                  token={token}
                  subjectId={subjectId}
                />
              )}
            </PatientMedicationCard>
          ))}
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
