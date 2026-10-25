import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { appointmentDetail } from '../scheduling/api'
import { nameOrId, readableStatus } from '../appointments/display'
import { readNote, appointmentPrescriptions, recordsError } from './api'
import { ConsultationNoteForm } from './ConsultationNoteForm'
import { MedicalCertificateForm } from './MedicalCertificateForm'
import { PrescriptionEditor } from './PrescriptionEditor'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { DocumentList } from '../documents/DocumentList'
import { PreviousVisitNotes } from './PreviousVisitNotes'
import { ReloadRecordsButton } from './ReloadRecordsButton'
import type { RecordFormState } from './useRecordFormState'

export function RecordWorkspace({
  appointmentId,
  token,
  subjectId,
}: {
  appointmentId: string
  token: string
  subjectId: string
}) {
  const [revision, setRevision] = useState(0)
  const cache = useQueryClient()
  const appointment = useQuery({
    queryKey: ['records', 'context', token, appointmentId],
    queryFn: ({ signal }) => appointmentDetail(appointmentId, signal),
    refetchInterval: 10000,
    retry: false,
    gcTime: 0,
  })
  if (appointment.isError)
    return (
      <ErrorState
        message={recordsError(appointment.error)}
        onRetry={() => void appointment.refetch()}
      />
    )
  if (!appointment.data)
    return <LoadingState message="Checking appointment..." />
  const context = appointment.data
  if (
    context.doctor_id !== subjectId ||
    context.appointment_id !== appointmentId
  )
    return (
      <ErrorState message="This appointment is unavailable to your account." />
    )
  return (
    <div className="space-y-5">
      <section
        className="rounded-2xl border border-teal-100 bg-teal-50/60 p-5"
        aria-label="Visit context"
      >
        <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-teal-800">
          Current visit
        </p>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="text-xs text-slate-600">Patient</dt>
            <dd className="mt-1 break-words font-semibold">
              {nameOrId(context.patient_name, context.patient_id)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-slate-600">Clinic</dt>
            <dd className="mt-1 break-words font-medium">
              {nameOrId(context.clinic_name, context.tenant_id)}
            </dd>
          </div>
          <div className="col-span-2 flex items-center justify-between border-t border-teal-100 pt-3">
            <dt className="text-slate-600">Session</dt>
            <dd className="rounded-full bg-white px-3 py-1 text-xs font-medium capitalize text-teal-900">
              {readableStatus(context.status)}
            </dd>
          </div>
        </dl>
      </section>
      <Records
        key={`${appointmentId}:${revision}`}
        appointmentId={appointmentId}
        tenantId={context.tenant_id}
        token={token}
        editable={context.status === 'in_progress'}
        onReload={() => {
          void appointment.refetch()
          for (const resource of ['workspace', 'mc']) {
            cache.removeQueries({
              queryKey: ['records', resource, token, appointmentId],
              exact: true,
            })
          }
          setRevision((value) => value + 1)
        }}
      />
      <PreviousVisitNotes
        key={appointmentId}
        appointment={context}
        token={token}
      />
      <DocumentList
        role="doctor"
        appointmentId={appointmentId}
        tenantId={context.tenant_id}
      />
    </div>
  )
}

function Records({
  appointmentId,
  tenantId,
  token,
  editable,
  onReload,
}: {
  appointmentId: string
  tenantId: string
  token: string
  editable: boolean
  onReload: () => void
}) {
  const [uncertain, setUncertain] = useState(false)
  const [noteState, setNoteState] = useState<RecordFormState>({
    dirty: false,
    busy: false,
  })
  const [mcState, setMcState] = useState<RecordFormState>({
    dirty: false,
    busy: false,
  })
  const [prescriptionState, setPrescriptionState] = useState<RecordFormState>({
    dirty: false,
    busy: false,
  })
  const dirty = noteState.dirty || mcState.dirty || prescriptionState.dirty
  const busy = noteState.busy || mcState.busy || prescriptionState.busy
  useEffect(() => {
    if (!dirty && !busy) return
    const warnBeforeLeaving = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeLeaving)
    return () => window.removeEventListener('beforeunload', warnBeforeLeaving)
  }, [dirty, busy])
  const records = useQuery({
    queryKey: ['records', 'workspace', token, appointmentId],
    queryFn: async ({ signal }) => {
      const [note, prescriptions] = await Promise.all([
        readNote(appointmentId, signal),
        appointmentPrescriptions(appointmentId, signal),
      ])
      return {
        note,
        prescription:
          prescriptions.find((item) => item.status !== 'voided') ??
          prescriptions.at(-1) ??
          null,
      }
    },
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  })
  if (records.isError)
    return (
      <ErrorState
        message={recordsError(records.error)}
        onRetry={() => void records.refetch()}
      />
    )
  if (!records.data || records.isFetching)
    return <LoadingState message="Loading clinical records..." />
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Clinical records</h2>
          <p className="mt-1 text-xs text-slate-600" role="status">
            {busy
              ? 'Saving changes…'
              : dirty
                ? 'You have unsaved changes.'
                : 'Drafts autosave after a short pause. Wait for Saved before completing the visit.'}
          </p>
        </div>
        <ReloadRecordsButton dirty={dirty} busy={busy} onReload={onReload} />
      </div>
      {!editable && (
        <p
          role="status"
          className="rounded-xl bg-slate-100 p-4 text-sm text-slate-600"
        >
          Read-only records. Editing is available while the consultation is in
          progress.
        </p>
      )}
      {uncertain && (
        <p
          role="alert"
          className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900"
        >
          A request could not be confirmed. Reload saved records to check its
          outcome before making further changes.
        </p>
      )}
      <ConsultationNoteForm
        appointmentId={appointmentId}
        note={records.data.note}
        editable={editable && !uncertain}
        onFailure={() => setUncertain(true)}
        onStateChange={setNoteState}
      />
      <MedicalCertificateForm
        appointmentId={appointmentId}
        token={token}
        editable={editable && !uncertain}
        onStateChange={setMcState}
      />
      <PrescriptionEditor
        appointmentId={appointmentId}
        tenantId={tenantId}
        token={token}
        prescription={records.data.prescription}
        editable={editable && !uncertain}
        onFailure={() => setUncertain(true)}
        onStateChange={setPrescriptionState}
      />
    </div>
  )
}
