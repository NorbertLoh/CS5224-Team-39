import type { ReactNode } from 'react'
import type { PortalRole } from '../app/portals'

export interface FeaturePage {
  path: string
  label: string
  element: ReactNode
  /** Set false for detail routes containing parameters. */
  navigation?: boolean
}

export interface FeatureRegistration {
  id: string
  pages: Partial<Record<PortalRole, FeaturePage[]>>
}
