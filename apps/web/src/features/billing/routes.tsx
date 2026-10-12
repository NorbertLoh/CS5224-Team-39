import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const billingFeature: FeatureRegistration = {
  id: 'billing',
  pages: {
    patient: [{ path: 'payments', label: 'Payments', element: <FeaturePlaceholder title="Payments" /> }],
    'clinic-admin': [{ path: 'payments', label: 'Payments', element: <FeaturePlaceholder title="Payments" /> }],
  },
}
