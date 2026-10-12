import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const clinicalRecordsFeature: FeatureRegistration = {
  id: 'clinical-records',
  pages: {
    patient: [{ path: 'prescriptions', label: 'Prescriptions', element: <FeaturePlaceholder title="Prescriptions" /> }],
    doctor: [{ path: 'records', label: 'Clinical records', element: <FeaturePlaceholder title="Clinical records" /> }],
  },
}
