import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
    <div className="space-y-4">
      <dl className="grid gap-2 text-sm">
        <div>
          <dt className="font-medium">Patient</dt>
          <dd className="break-all">
            {nameOrId(context.patient_name, context.patient_id)}
          </dd>
        </div>
        <div>
          <dt className="font-medium">Clinic</dt>
          <dd className="break-all">
            {nameOrId(context.clinic_name, context.tenant_id)}
          </dd>
        </div>
        <div>
          <dt className="font-medium">Session</dt>
          <dd className="capitalize">{readableStatus(context.status)}</dd>
        </div>
      </dl>
      <button
        className="rounded border px-4 py-2"
        onClick={() => {
          void appointment.refetch()
          setRevision((value) => value + 1)
        }}
      >
        Reload records and discard unsaved changes
      </button>
      <Records
        key={`${appointmentId}:${revision}`}
        appointmentId={appointmentId}
        tenantId={context.tenant_id}
        token={token}
        editable={context.status === 'in_progress'}
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
}: {
  appointmentId: string
  tenantId: string
  token: string
  editable: boolean
}) {
  const [uncertain, setUncertain] = useState(false)
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
    <div className="space-y-6">
      {!editable && (
        <p role="status">
          Records are read-only while this appointment is not in progress.
        </p>
      )}
      {uncertain && (
        <p role="alert">
          Reload records before making further changes to check the last
          request's outcome.
        </p>
      )}
      <ConsultationNoteForm
        appointmentId={appointmentId}
        note={records.data.note}
        editable={editable && !uncertain}
        onFailure={() => setUncertain(true)}
      />
      <MedicalCertificateForm
        appointmentId={appointmentId}
        token={token}
        editable={editable && !uncertain}
      />
      <PrescriptionEditor
        appointmentId={appointmentId}
        tenantId={tenantId}
        token={token}
        prescription={records.data.prescription}
        editable={editable && !uncertain}
        onFailure={() => setUncertain(true)}
      />
    </div>
  )
}
