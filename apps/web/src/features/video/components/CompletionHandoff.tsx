import {
  appointmentPrescriptions,
  readMedicalCertificate,
} from '@/features/records/api'
import { PrescriptionDetails } from '@/features/records/prescriptions/PrescriptionDetails'
import type { Appointment } from '@/features/scheduling/api'
import { ConsultationActions } from '@/features/video/components/ConsultationActions'
import { useQuery } from '@tanstack/react-query'

export function CompletionHandoff({
  appointment,
  token,
}: {
  appointment: Appointment
  token: string
}) {
  const completion = useQuery({
    queryKey: ['records', 'completion', token, appointment.appointment_id],
    queryFn: async ({ signal }) => {
      const [mc, prescriptions] = await Promise.all([
        readMedicalCertificate(appointment.appointment_id, signal),
        appointmentPrescriptions(appointment.appointment_id, signal),
      ])
      return { mc, prescriptions }
    },
    retry: false,
    gcTime: 0,
  })
  if (completion.isPending)
    return <p role="status">Checking completion handoff...</p>
  const prescriptions = completion.data?.prescriptions ?? []
  const finished =
    completion.data?.mc?.finalized_at &&
    !prescriptions.some((prescription) => prescription.status === 'draft')
  return (
    <>
      {finished ? (
        <p role="status">
          Prescription, consultation completion and MC decision confirmed.
        </p>
      ) : (
        <>
          <p role="alert">
            {completion.isError
              ? 'Could not check the saved prescription and MC decision.'
              : 'The saved prescription or MC decision still needs finalising.'}{' '}
            Retry completion to finish the saved records.
          </p>
          <ConsultationActions appointment={appointment} />
        </>
      )}
      {prescriptions.map((prescription) => (
        <PrescriptionDetails
          key={prescription.prescription_id}
          prescription={prescription}
        />
      ))}
    </>
  )
}
