import { useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { listPrescriptions, readPrescription, recordsError } from './api'
import { PrescriptionDetails } from './PrescriptionDetails'
import { PrescriptionSummary } from './PrescriptionSummary'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function PatientPrescriptions() {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify prescription access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data || !identity.token)
    return <LoadingState message="Loading prescription access..." />
  return (
    <PatientList
      key={identity.token}
      token={identity.token}
      subjectId={identity.data.subject_id}
    />
  )
}
function PatientList({
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
  })
  const prescriptions =
    query.data?.pages
      .flatMap((page) => page.items)
      .filter((item) => item.patient_id === subjectId) ?? []
  return (
    <section
      className="mt-8 space-y-4 rounded-xl border p-6"
      aria-labelledby="prescription-heading"
    >
      <h2 id="prescription-heading" className="text-xl font-semibold">
        Prescriptions
      </h2>
      <button
        className="rounded border px-4 py-2"
        disabled={query.isFetching}
        onClick={() => {
          setSelected(null)
          void query.refetch()
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
            <div key={prescription.prescription_id} className="space-y-3">
              <PrescriptionSummary
                prescription={prescription}
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
                <PatientDetail
                  key={selected}
                  id={selected}
                  token={token}
                  subjectId={subjectId}
                />
              )}
            </div>
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
function PatientDetail({
  id,
  token,
  subjectId,
}: {
  id: string
  token: string
  subjectId: string
}) {
  const query = useQuery({
    queryKey: ['records', 'prescription', token, id],
    queryFn: ({ signal }) => readPrescription(id, signal),
    retry: false,
    gcTime: 0,
  })
  if (query.isError)
    return (
      <ErrorState
        message={recordsError(query.error)}
        onRetry={() => void query.refetch()}
      />
    )
  if (!query.data || query.isFetching)
    return <LoadingState message="Loading prescription details..." />
  if (query.data.patient_id !== subjectId || query.data.prescription_id !== id)
    return (
      <ErrorState message="This prescription is unavailable to your account." />
    )
  return <PrescriptionDetails prescription={query.data} />
}
