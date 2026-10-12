import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const fulfilmentFeature: FeatureRegistration = {
  id: 'fulfilment',
  pages: {
    patient: [{ path: 'deliveries', label: 'Deliveries', element: <FeaturePlaceholder title="Deliveries" /> }],
    'clinic-admin': [{ path: 'fulfilment', label: 'Fulfilment', element: <FeaturePlaceholder title="Fulfilment" /> }],
  },
}
