import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AppointmentDetails } from './AppointmentDetails'
import {
  appointmentDetail,
  cancelAppointment,
  canCancel,
  schedulingError,
} from '../scheduling/api'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { DocumentList } from '../documents/DocumentList'
import type { AppointmentRole } from './types'
import { AppointmentJoinButton } from './AppointmentJoinButton'
import { AppointmentPaymentAction } from './AppointmentPaymentAction'

export function LiveAppointmentDetails({
  id,
  token,
  subjectId,
  role,
  onClose,
}: {
  id: string
  token?: string
  subjectId: string
  role: AppointmentRole
  onClose: () => void
}) {
  const cache = useQueryClient()
  const [reason, setReason] = useState('')
  const detail = useQuery({
    queryKey: ['scheduling', 'appointment', token, id],
    queryFn: () => appointmentDetail(id),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
  const cancel = useMutation({
    mutationFn: () => cancelAppointment(id, reason.trim()),
    onSuccess: (appointment) => {
      cache.setQueryData(['scheduling', 'appointment', token, id], appointment)
      setReason('')
    },
    onSettled: async () => {
      await cache.invalidateQueries({ queryKey: ['scheduling'] })
    },
    retry: false,
  })
  if (detail.isPending)
    return <LoadingState message="Loading appointment details..." />
  if (detail.isError)
    return (
      <ErrorState
        message={schedulingError(detail.error)}
        onRetry={() => void detail.refetch()}
      />
    )
  const appointment = detail.data
  const allowed =
    (role === 'clinic_admin' ||
      (role === 'patient' && appointment.patient_id === subjectId)) &&
    canCancel(appointment)
  return (
    <div className="space-y-4">
      <AppointmentDetails appointment={appointment} onClose={onClose} />
      {role === 'patient' && appointment.patient_id === subjectId && (
        <AppointmentPaymentAction appointment={appointment} />
      )}
      {allowed && (
        <form
          className="space-y-3 rounded border p-4"
          onSubmit={(event) => {
            event.preventDefault()
            cancel.mutate()
          }}
        >
          <label className="flex flex-col gap-2">
            Cancellation reason
            <textarea
              className="rounded border p-2"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              required
              maxLength={2000}
              disabled={cancel.isPending}
            />
          </label>
          <p className="text-sm text-slate-600">
            Cancelling releases this booking. Paid bookings require refund
            review; this does not issue a provider refund.
          </p>
          <button
            type="submit"
            className="rounded border px-4 py-2"
            disabled={cancel.isPending || !reason.trim() || /[<>]/.test(reason)}
          >
            {cancel.isPending ? 'Cancelling...' : 'Cancel appointment'}
          </button>
        </form>
      )}
      {cancel.isError && <ErrorState message={schedulingError(cancel.error)} />}
      {cancel.isSuccess && <p role="status">Appointment cancelled.</p>}
      {(role === 'patient' || role === 'doctor') && (
        <AppointmentJoinButton
          appointment={appointment}
          role={role}
          subjectId={subjectId}
        />
      )}
      {((role === 'patient' && appointment.patient_id === subjectId) ||
        (role === 'doctor' && appointment.doctor_id === subjectId)) && (
        <DocumentList
          key={appointment.appointment_id}
          role={role as 'patient' | 'doctor'}
          appointmentId={appointment.appointment_id}
          tenantId={appointment.tenant_id}
        />
      )}
    </div>
  )
}
