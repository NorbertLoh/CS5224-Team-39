import { FeaturePlaceholder } from '../FeaturePlaceholder'
import type { FeatureRegistration } from '../types'

export const documentsFeature: FeatureRegistration = {
  id: 'documents',
  pages: {
    patient: [{ path: 'documents', label: 'Documents', element: <FeaturePlaceholder title="Documents" /> }],
  },
}
