import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { documentsError, listDocuments } from '@/features/documents/api'
import { DocumentRow } from '@/features/documents/DocumentRow'
import { VisitDocumentList } from '@/features/documents/VisitDocumentList'
import { useSchedulingIdentity } from '@/features/scheduling/useSchedulingIdentity'
import { hasRole } from '@/navigation/access'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useId } from 'react'

type Props = {
  role: 'patient' | 'doctor'
  appointmentId?: string
  tenantId?: string
  headingLevel?: 1 | 2
}

export function DocumentList(props: Props) {
  const identity = useSchedulingIdentity()
  if (!identity.token) return <p>Sign in to view documents.</p>
  if (identity.isError)
    return (
      <ErrorState
        message="Could not verify document access."
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data)
    return <LoadingState message="Checking document access..." />
  if (!hasRole(identity.data, props.role))
    return (
      <ErrorState message="These documents are unavailable to your account." />
    )
  const scope = JSON.stringify(identity.data)
  return (
    <DocumentResults
      key={`${identity.token}:${scope}:${props.appointmentId ?? ''}:${props.tenantId ?? ''}`}
      {...props}
      token={identity.token}
      scope={scope}
    />
  )
}

export function DocumentResults({
  role,
  appointmentId,
  tenantId,
  token,
  scope,
  headingLevel = 2,
}: Props & { token: string; scope: string }) {
  const headingId = useId()
  const groupByVisit = role === 'patient' && !appointmentId
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  const query = useInfiniteQuery({
    queryKey: [
      'documents',
      token,
      scope,
      appointmentId ?? null,
      tenantId ?? null,
    ],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listDocuments(appointmentId, pageParam, signal),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
  const items = query.data?.pages.flatMap((page) => page.items) ?? []
  const invalid = items.some(
    (item) =>
      (appointmentId && item.appointment_id !== appointmentId) ||
      (tenantId && item.tenant_id !== tenantId),
  )
  return (
    <section
      aria-labelledby={headingId}
      className="mt-6 space-y-4 rounded-xl border bg-white p-5 sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Heading
            id={headingId}
            className={
              headingLevel === 1
                ? 'text-3xl font-semibold'
                : 'text-xl font-semibold'
            }
          >
            Documents
          </Heading>
          <p className="mt-1 text-sm text-slate-600">
            {appointmentId
              ? 'PDFs for this appointment.'
              : groupByVisit
                ? 'Your PDFs grouped by visit. Expand a visit to download its documents.'
                : 'Your available prescriptions, receipts and medical certificates.'}
          </p>
        </div>
        <button
          type="button"
          className="rounded border px-4 py-2 text-sm"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh documents
        </button>
      </div>
      {query.isPending ? (
        <LoadingState message="Loading documents..." />
      ) : invalid ? (
        <ErrorState message="These documents are unavailable to your account." />
      ) : query.isError ? (
        <ErrorState
          message={documentsError(query.error)}
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          {!items.length && (
            <p role="status" className="text-sm text-slate-600">
              No documents available yet. Refresh after your document has been
              prepared.
            </p>
          )}
          {items.length > 0 &&
            (groupByVisit ? (
              <VisitDocumentList documents={items} token={token} />
            ) : (
              <ul className="divide-y">
                {items.map((item) => (
                  <li key={item.document_id}>
                    <DocumentRow document={item} token={token} />
                  </li>
                ))}
              </ul>
            ))}
          {query.hasNextPage && (
            <button
              type="button"
              className="rounded border px-4 py-2"
              disabled={query.isFetching}
              onClick={() => void query.fetchNextPage()}
            >
              {query.isFetchingNextPage
                ? 'Loading more...'
                : 'Load more documents'}
            </button>
          )}
        </>
      )}
    </section>
  )
}
