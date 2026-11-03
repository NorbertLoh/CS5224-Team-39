import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import type { ApplicationFields, DoctorApplication } from './api'
import {
  downloadEvidence,
  myApplication,
  submitApplication,
  uploadEvidence,
} from './api'
import { ApiError } from '@/lib/api'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { FormEvent } from 'react'

export function DoctorApplicationPage() {
  const application = useQuery({
    queryKey: ['doctor-application', readSession()?.accessToken],
    queryFn: ({ signal }) => myApplication(signal),
    refetchInterval: 30000,
  })
  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <p className="text-sm font-medium text-teal-700">
        Professional registration
      </p>
      <h1 className="mt-2 text-3xl font-semibold">Join as a doctor</h1>
      <p className="mt-3 text-slate-600">
        Submit your professional details for platform review. You can join a
        clinic before approval; clinical access starts once you are approved and
        your clinic membership is active.
      </p>
      {application.isPending ? (
        <LoadingState message="Loading your application..." />
      ) : application.isError ? (
        <ErrorState
          message="Could not load your application."
          onRetry={() => void application.refetch()}
        />
      ) : (
        <ApplicationForm
          key={`${application.data?.revision ?? 0}:${application.data?.status ?? 'new'}`}
          application={application.data}
        />
      )}
    </main>
  )
}

function ApplicationForm({
  application,
}: {
  application: DoctorApplication | null
}) {
  const client = useQueryClient()
  const [fields, setFields] = useState<ApplicationFields>({
    legal_name: application?.legal_name ?? '',
    licence_number: application?.licence_number ?? '',
    licensing_authority: application?.licensing_authority ?? '',
    specialty: application?.specialty ?? '',
  })
  const [file, setFile] = useState<File | null>(null)
  const [documentId, setDocumentId] = useState(application?.document_id ?? '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const editable =
    !application ||
    application.status === 'rejected' ||
    application.status === 'revoked'

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (busy) return
    if (
      file &&
      (file.size > 5 * 1024 * 1024 ||
        !['application/pdf', 'image/png', 'image/jpeg'].includes(file.type))
    ) {
      setMessage('Choose a PDF, PNG or JPEG file no larger than 5 MB.')
      return
    }
    setBusy(true)
    setMessage('')
    try {
      const evidence = file ? await uploadEvidence(file) : documentId
      setDocumentId(evidence)
      setFile(null)
      await submitApplication(fields, evidence, application?.revision ?? 0)
      await client.invalidateQueries({ queryKey: ['doctor-application'] })
      await client.invalidateQueries({ queryKey: ['identity'] })
    } catch (error) {
      setMessage(
        error instanceof ApiError && error.status === 409
          ? 'Your application has changed. Reload the page to see its current status.'
          : 'Could not submit your application. Your details are still here. Check the file and try again.',
      )
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {application && (
        <section
          className="mt-6 rounded-xl border bg-slate-50 p-5"
          aria-label="Application status"
        >
          <h2 className="font-semibold">
            {application.status === 'pending'
              ? 'Pending review'
              : application.status === 'approved'
                ? 'Doctor application approved'
                : application.status === 'revoked'
                  ? 'Approval revoked — resubmission required'
                  : 'Changes required'}
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            {application.status === 'pending'
              ? 'A platform administrator will review your details and supporting document. You can continue using your patient account while you wait.'
              : application.status === 'approved'
                ? 'Your verification is complete. Ask your clinic administrator to add or activate your clinic membership if you do not see the doctor workspace.'
                : application.status === 'revoked'
                  ? `Your doctor access has been disabled. Update your details and resubmit for review. Reason: ${application.rejection_reason}`
                  : application.rejection_reason}
          </p>
        </section>
      )}
      <form
        onSubmit={(event) => void submit(event)}
        className="mt-6 rounded-xl border bg-white p-6"
      >
        <fieldset
          disabled={busy || !editable}
          className="grid gap-5 sm:grid-cols-2"
        >
          <legend className="mb-4 text-lg font-semibold">
            Professional details
          </legend>
          {(
            [
              ['legal_name', 'Full name on licence', 200],
              ['licence_number', 'Medical licence / registration number', 100],
              ['licensing_authority', 'Licensing authority', 200],
              ['specialty', 'Specialty / area of practice', 200],
            ] as const
          ).map(([key, label, max]) => (
            <label key={key} className="grid gap-2 text-sm">
              {label}
              <input
                required
                maxLength={max}
                value={fields[key]}
                onChange={(event) =>
                  setFields({ ...fields, [key]: event.target.value })
                }
                className="rounded-md border p-3"
              />
            </label>
          ))}
          {editable && (
            <label className="grid min-w-0 gap-3 rounded-xl border border-dashed border-teal-300 bg-teal-50/40 p-5 text-sm sm:col-span-2">
              <span className="font-medium text-slate-900">
                Licence and supporting evidence
              </span>
              <input
                type="file"
                accept="application/pdf,image/png,image/jpeg"
                required={!documentId}
                aria-describedby="doctor-evidence-help"
                className="w-full min-w-0 cursor-pointer rounded-lg text-sm text-slate-600 outline-none file:mr-4 file:cursor-pointer file:rounded-lg file:border-0 file:bg-teal-700 file:px-5 file:py-3 file:text-sm file:font-semibold file:text-white file:transition-colors hover:file:bg-teal-800 focus-visible:ring-2 focus-visible:ring-teal-600 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:file:cursor-not-allowed"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null)
                }}
              />
              <span id="doctor-evidence-help" className="text-slate-600">
                Upload a PDF, PNG or JPEG, up to 5 MB. Combine multiple pages
                into one PDF. Only you and platform reviewers can download it.{' '}
                {documentId &&
                  'Your previously uploaded document will be used unless you choose a replacement.'}
              </span>
            </label>
          )}
          {editable && (
            <Button type="submit" className="justify-self-start">
              {busy
                ? 'Submitting...'
                : application
                  ? 'Resubmit application'
                  : 'Submit for review'}
            </Button>
          )}
        </fieldset>
      </form>
      {documentId && (
        <Button
          variant="outline"
          className="mt-4"
          disabled={busy}
          onClick={() => {
            setMessage('')
            void downloadEvidence(documentId).catch(() =>
              setMessage(
                'Could not download your supporting document. Try again.',
              ),
            )
          }}
        >
          Download supporting document
        </Button>
      )}
      <p role="status" className="mt-4 text-sm">
        {message}
      </p>
    </>
  )
}
