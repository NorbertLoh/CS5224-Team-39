import { useQueries, useQuery } from '@tanstack/react-query'
import { clinicDoctors, listClinics } from '../clinics/api'
import type { Appointment } from '../scheduling/api'

async function clinicNames() {
  const names = new Map<string, string>()
  let cursor: string | null = null
  do {
    const page = await listClinics(cursor)
    for (const clinic of page.items) names.set(clinic.tenant_id, clinic.name)
    cursor = page.next_cursor
  } while (cursor)
  return names
}

async function doctorNames(tenantId: string) {
  const names = new Map<string, string>()
  let cursor: string | null = null
  do {
    const page = await clinicDoctors(tenantId, cursor)
    for (const doctor of page.items) names.set(doctor.doctor_id, doctor.display_name)
    cursor = page.next_cursor
  } while (cursor)
  return names
}

// Preserve booking-time names; use the public directories for legacy bookings.
export function useAppointmentNames(appointments: Appointment[]) {
  const clinics = useQuery({
    queryKey: ['appointment-clinic-names'],
    queryFn: clinicNames,
    enabled: appointments.some((appointment) => !appointment.clinic_name),
    staleTime: 60000,
  })
  const tenantIds = [...new Set(
    appointments.filter((appointment) => !appointment.doctor_name)
      .map((appointment) => appointment.tenant_id),
  )]
  const doctors = useQueries({
    queries: tenantIds.map((tenantId) => ({
      queryKey: ['appointment-doctor-names', tenantId],
      queryFn: () => doctorNames(tenantId),
      staleTime: 60000,
    })),
  })
  const doctorsByClinic = new Map(tenantIds.map((id, index) => [id, doctors[index].data]))
  return appointments.map((appointment) => ({
    ...appointment,
    clinic_name: appointment.clinic_name || clinics.data?.get(appointment.tenant_id)
      || 'Clinic name unavailable',
    doctor_name: appointment.doctor_name
      || doctorsByClinic.get(appointment.tenant_id)?.get(appointment.doctor_id)
      || 'Doctor name unavailable',
  }))
}
