import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const tenantFeature: FeatureRegistration = {
  id: 'tenant',
  pages: {
    'clinic-admin': [
      { path: 'profile', label: 'Clinic profile', element: <FeaturePlaceholder title="Clinic profile" /> },
      { path: 'staff', label: 'Staff', element: <FeaturePlaceholder title="Staff" /> },
    ],
    'platform-admin': [{ path: 'clinics', label: 'Clinics and commissions', element: <FeaturePlaceholder title="Clinics and commissions" /> }],
  },
}
