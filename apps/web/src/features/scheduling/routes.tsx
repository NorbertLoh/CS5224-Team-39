import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const schedulingFeature: FeatureRegistration = {
  id: 'scheduling',
  pages: {
    patient: [{ path: 'appointments', label: 'Appointments', element: <FeaturePlaceholder title="Appointments" /> }],
    doctor: [
      { path: 'appointments', label: 'Appointments', element: <FeaturePlaceholder title="Appointments" /> },
      { path: 'availability', label: 'Availability', element: <FeaturePlaceholder title="Availability" /> },
    ],
    'clinic-admin': [{ path: 'appointments', label: 'Appointments', element: <FeaturePlaceholder title="Appointments" /> }],
  },
}
