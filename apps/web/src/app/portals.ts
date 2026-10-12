export const portals = {
  patient: { title: 'Patient portal', description: 'Appointments, records and medication delivery.' },
  doctor: { title: 'Doctor portal', description: 'Availability, consultations and clinical records.' },
  'clinic-admin': { title: 'Clinic dashboard', description: 'Manage your clinic and daily operations.' },
  'platform-admin': { title: 'Platform administration', description: 'Manage clinics across the platform.' },
} as const

export type PortalRole = keyof typeof portals
