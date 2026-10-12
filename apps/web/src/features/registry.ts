import { billingFeature } from './billing/routes'
import { clinicalRecordsFeature } from './clinical-records/routes'
import { documentsFeature } from './documents/routes'
import { fulfilmentFeature } from './fulfilment/routes'
import { schedulingFeature } from './scheduling/routes'
import { tenantFeature } from './tenant/routes'
import type { PortalRole } from '../app/portals'
import type { FeatureRegistration } from './types'

const features: FeatureRegistration[] = [
  schedulingFeature,
  clinicalRecordsFeature,
  documentsFeature,
  billingFeature,
  fulfilmentFeature,
  tenantFeature,
]

export function pagesFor(role: PortalRole) {
  return features.flatMap(feature => feature.pages[role] ?? [])
}
