import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { documentsError, listDocuments } from '@/features/documents/api'
import { PastDocumentRow } from '@/features/documents/PastDocumentRow'
import { pastDocumentGroups } from '@/features/documents/pastDocumentGroups'
import { previousVisitDocuments } from '@/features/documents/previousVisitDocuments'
import { ChevronDown, FileText } from 'lucide-react'
import { DocumentRow } from '@/features/documents/DocumentRow'
import { VisitDocumentList } from '@/features/documents/VisitDocumentList'
import { useSchedulingIdentity } from '@/features/scheduling/useSchedulingIdentity'
import type { Appointment } from '@/features/scheduling/api'
import { hasRole } from '@/navigation/access'
import { useInfiniteQuery } from '@tanstack/react-query'
import { useId } from 'react'

type Props = {
  role: 'patient' | 'doctor'
  appointmentId?: string
  tenantId?: string
  previousVisitsFor?: Appointment
  headingLevel?: 1 | 2
  variant?: 'default' | 'past'
  autoRefresh?: boolean
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
      key={`${identity.token}:${scope}:${props.appointmentId ?? props.previousVisitsFor?.appointment_id ?? ''}:${props.tenantId ?? ''}`}
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
  previousVisitsFor,
  token,
  scope,
  headingLevel = 2,
  variant = 'default',
  autoRefresh = false,
}: Props & { token: string; scope: string }) {
  const headingId = useId()
  const collapsible = variant === 'past' && !!previousVisitsFor
  const Container = collapsible ? 'details' : 'section'
  const PastHeader = collapsible ? 'summary' : 'div'
  const groupByVisit = role === 'patient' && !appointmentId
  const standalone = groupByVisit && headingLevel === 1
  const Heading = headingLevel === 1 ? 'h1' : 'h2'
  const query = useInfiniteQuery({
    queryKey: [
      'documents',
      token,
      scope,
      appointmentId ?? null,
      tenantId ?? null,
      previousVisitsFor?.appointment_id ?? null,
      previousVisitsFor?.patient_id ?? null,
      previousVisitsFor?.starts_at ?? null,
    ],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) =>
      previousVisitsFor
        ? previousVisitDocuments(previousVisitsFor, pageParam, signal)
        : {
            ...(await listDocuments(appointmentId, pageParam, signal)),
            visits: [] as Appointment[],
          },
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: autoRefresh ? 5000 : variant === 'past' ? 10000 : false,
  })
  const items = query.data?.pages.flatMap((page) => page.items) ?? []
  const visits = query.data?.pages.flatMap((page) => page.visits ?? []) ?? []
  const pastGroups = pastDocumentGroups(items, visits)
  const invalid = items.some(
    (item) =>
      (appointmentId && item.appointment_id !== appointmentId) ||
      (tenantId && item.tenant_id !== tenantId) ||
      (previousVisitsFor &&
        !visits.some(
          (visit) =>
            visit.appointment_id === item.appointment_id &&
            visit.tenant_id === item.tenant_id,
        )),
  )
  return (
    <Container
      aria-labelledby={headingId}
      className={
        collapsible
          ? 'group/history rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm open:space-y-3'
          : variant === 'past'
            ? 'space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm'
            : standalone
              ? 'space-y-6'
              : 'mt-6 space-y-4 rounded-xl border bg-white p-5 sm:p-6'
      }
    >
      {variant === 'past' ? (
        <PastHeader
          className={`flex items-center gap-3 ${collapsible ? 'cursor-pointer list-none rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 [&::-webkit-details-marker]:hidden' : ''}`}
        >
          <span className="rounded-lg bg-slate-100 p-2 text-slate-600">
            <FileText aria-hidden="true" size={18} />
          </span>
          <h3 id={headingId} className="font-semibold">
            Past documents
          </h3>
          {collapsible && (
            <ChevronDown
              aria-hidden="true"
              size={20}
              className="ml-auto shrink-0 text-slate-500 transition-transform group-open/history:rotate-180"
            />
          )}
        </PastHeader>
      ) : (
        <div
          className={`flex flex-wrap justify-between gap-3 ${standalone ? 'items-start' : 'items-center'}`}
        >
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
      )}
      {collapsible && (
        <p className="text-sm text-slate-600">
          PDFs grouped by consultation. Open a visit to view its documents.
        </p>
      )}
      {query.isPending ? (
        <LoadingState message="Loading documents..." />
      ) : invalid ? (
        <ErrorState message="These documents are unavailable to your account." />
      ) : query.isError ? (
        <ErrorState
          message={documentsError(query.error)}
          onRetry={() =>
            void (query.isFetchNextPageError
              ? query.fetchNextPage()
              : query.refetch())
          }
        />
      ) : (
        <>
          {!items.length && (
            <p role="status" className="text-sm text-slate-600">
              {previousVisitsFor
                ? 'No documents from previous consultations.'
                : autoRefresh
                  ? 'No documents available yet. New PDFs will appear here as they are prepared.'
                  : 'No documents available yet. Refresh after your document has been prepared.'}
            </p>
          )}
          {items.length > 0 &&
            (variant === 'past' && previousVisitsFor ? (
              <div className="space-y-4">
                {pastGroups.map(({ visit, documents }) => (
                  <PastDocumentRow
                    key={`${visit.tenant_id}:${visit.appointment_id}`}
                    visit={visit}
                    documents={documents}
                    token={token}
                    historyFor={previousVisitsFor?.appointment_id}
                  />
                ))}
              </div>
            ) : groupByVisit ? (
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
                : previousVisitsFor
                  ? 'Load documents from older visits'
                  : 'Load more documents'}
            </button>
          )}
        </>
      )}
    </Container>
  )
}
