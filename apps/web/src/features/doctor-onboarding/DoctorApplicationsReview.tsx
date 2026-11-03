import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import { useState } from 'react'
import type { DoctorApplication } from './api'
import {
  applicationHistory,
  downloadEvidence,
  listApplications,
  reviewApplication,
} from './api'

export function DoctorApplicationsReview() {
  const [status, setStatus] = useState<DoctorApplication['status']>('pending')
  const applications = useInfiniteQuery({
    queryKey: ['doctor-applications', readSession()?.accessToken, status],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      listApplications(status, pageParam, signal),
    getNextPageParam: (page) =>
      page.length === 25 ? page.at(-1)?.subject_id : undefined,
  })
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <a href="/platform-admin/clinics" className="text-sm underline">
        Manage clinics
      </a>
      <h1 className="mt-4 text-3xl font-semibold">Doctor applications</h1>
      <p className="mt-3 text-slate-600">
        Review the licence and supporting evidence before granting doctor
        eligibility. Clinic access still requires an active membership.
      </p>
      <label className="mt-6 flex items-center gap-3 text-sm">
        Status
        <select
          className="rounded-md border p-2"
          value={status}
          onChange={(event) =>
            setStatus(event.target.value as DoctorApplication['status'])
          }
        >
          <option value="pending">Pending review</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="revoked">Revoked</option>
        </select>
      </label>
      {applications.isPending ? (
        <LoadingState message="Loading applications..." />
      ) : applications.isError ? (
        <ErrorState
          message="Could not load applications."
          onRetry={() => void applications.refetch()}
        />
      ) : (
        <>
          {!applications.data.pages.some((page) => page.length) && (
            <p className="mt-6 text-slate-600">
              No applications with this status.
            </p>
          )}
          <div className="mt-6 grid gap-5">
            {applications.data.pages.flat().map((application) => (
              <ReviewCard
                key={`${application.subject_id}:${application.revision}:${application.status}`}
                application={application}
              />
            ))}
          </div>
          {applications.hasNextPage && (
            <Button
              className="mt-5"
              disabled={applications.isFetching}
              onClick={() => void applications.fetchNextPage()}
            >
              Load more applications
            </Button>
          )}
        </>
      )}
    </main>
  )
}

function ReviewCard({ application }: { application: DoctorApplication }) {
  const client = useQueryClient()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const history = useQuery({
    queryKey: [
      'doctor-application-history',
      readSession()?.accessToken,
      application.subject_id,
      application.revision,
      application.status,
    ],
    queryFn: () => applicationHistory(application.subject_id),
    enabled: showHistory,
  })
  async function decide(decision: 'approved' | 'rejected' | 'revoked') {
    if (busy) return
    if (!reason.trim()) {
      setMessage(
        'Enter a review note. For rejection or revocation, explain what the applicant needs to change.',
      )
      return
    }
    setBusy(true)
    setMessage('')
    try {
      await reviewApplication(application, decision, reason.trim())
      await Promise.all([
        client.invalidateQueries({ queryKey: ['doctor-applications'] }),
        client.invalidateQueries({ queryKey: ['staff'] }),
        client.invalidateQueries({ queryKey: ['identity'] }),
        client.invalidateQueries({ queryKey: ['doctor-application'] }),
        client.invalidateQueries({ queryKey: ['clinic-doctors'] }),
      ])
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 409
          ? 'This application has already changed. Refresh the list before reviewing it.'
          : 'Could not save the review. Check your permissions and try again.',
      )
    } finally {
      setBusy(false)
    }
  }
  return (
    <article className="rounded-xl border bg-white p-6">
      <h2 className="text-xl font-semibold">{application.legal_name}</h2>
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-slate-500">Licence / registration number</dt>
          <dd>{application.licence_number}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Licensing authority</dt>
          <dd>{application.licensing_authority}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Specialty</dt>
          <dd>{application.specialty}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Submitted</dt>
          <dd>
            {new Date(application.submitted_at).toLocaleString('en-SG', {
              timeZone: 'Asia/Singapore',
            })}{' '}
            SGT · Submission {application.revision}
          </dd>
        </div>
      </dl>
      {application.rejection_reason && (
        <p className="mt-3 text-sm">
          {application.status === 'revoked'
            ? 'Revocation reason'
            : 'Rejection reason'}
          : {application.rejection_reason}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-3">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() => {
            setMessage('')
            void downloadEvidence(application.document_id).catch(() =>
              setMessage('Could not download the document. Try again.'),
            )
          }}
        >
          Download supporting document
        </Button>
        <Button
          variant="outline"
          onClick={() => setShowHistory(!showHistory)}
          aria-expanded={showHistory}
        >
          Review history
        </Button>
      </div>
      {showHistory && (
        <div className="mt-4 rounded-lg bg-slate-50 p-4 text-sm">
          {history.isPending ? (
            <p>Loading history...</p>
          ) : history.isError ? (
            <ErrorState
              message="Could not load history."
              onRetry={() => void history.refetch()}
            />
          ) : (
            <ol className="grid gap-3">
              {history.data.map((event) => (
                <li key={event.event_id}>
                  <p className="font-medium">
                    Submission {event.snapshot.revision}: {event.action} ·{' '}
                    {new Date(event.created_at).toLocaleString('en-SG', {
                      timeZone: 'Asia/Singapore',
                    })}{' '}
                    SGT
                  </p>
                  <p>
                    {event.snapshot.legal_name} ·{' '}
                    {event.snapshot.licence_number} ·{' '}
                    {event.snapshot.licensing_authority} ·{' '}
                    {event.snapshot.specialty}
                  </p>
                  {event.snapshot.review_reason && (
                    <p>{event.snapshot.review_reason}</p>
                  )}
                  <p className="text-xs text-slate-500">
                    Actor: {event.actor_id}
                  </p>
                  <button
                    type="button"
                    className="mt-1 underline"
                    onClick={() =>
                      void downloadEvidence(event.snapshot.document_id).catch(
                        () =>
                          setMessage('Could not download historical evidence.'),
                      )
                    }
                  >
                    Download evidence for this submission
                  </button>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      {(application.status === 'pending' ||
        application.status === 'approved') && (
        <fieldset disabled={busy} className="mt-5 grid gap-3">
          {application.status === 'approved' && (
            <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Revoking approval disables doctor access across all clinics. The
              doctor must resubmit and be approved again. Clinic memberships are
              retained.
            </p>
          )}
          <label className="grid gap-2 text-sm">
            {application.status === 'approved'
              ? 'Reason for revocation and required corrections'
              : 'Review note / rejection reason'}
            <textarea
              maxLength={2000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              className="rounded-md border p-3"
            />
          </label>
          <div className="flex gap-3">
            {application.status === 'approved' ? (
              <Button
                variant="destructive"
                onClick={() => void decide('revoked')}
              >
                {busy ? 'Revoking...' : 'Revoke approval for resubmission'}
              </Button>
            ) : (
              <>
                <Button onClick={() => void decide('approved')}>
                  {busy ? 'Saving...' : 'Approve doctor'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => void decide('rejected')}
                >
                  Reject application
                </Button>
              </>
            )}
          </div>
        </fieldset>
      )}
      <p role="status" className="mt-3 text-sm">
        {message}
      </p>
    </article>
  )
}
