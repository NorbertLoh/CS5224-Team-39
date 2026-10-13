import { profileDraft, profileUpdate, validateProfile, validLogoUrl } from './profile'
import type { ClinicProfile } from './profile'

type SavedDemo = { profile: ClinicProfile; logoPreview: string | null }
type DemoStorage = Pick<Storage, 'getItem' | 'setItem'>

function key(tenantId: string) {
  return `telelink.demo.clinic-profile.${tenantId}`
}

export function readDemoProfile(tenantId: string, fallback: ClinicProfile, storage: DemoStorage = localStorage): SavedDemo {
  try {
    const saved = JSON.parse(storage.getItem(key(tenantId)) || 'null')
    if (saved && Object.keys(validateProfile(profileDraft(saved.profile))).length === 0) {
      const preview = saved.logoPreview
      const validPreview = typeof preview === 'string' && preview.length <= 4 * 1024 * 1024 && (
        validLogoUrl(preview) || /^data:image\/(png|jpeg|webp);base64,/.test(preview)
      )
      return { profile: profileUpdate(profileDraft(saved.profile)), logoPreview: validPreview ? preview : null }
    }
  } catch { /* Missing, corrupt or blocked browser storage uses the agreed fixture. */ }
  return { profile: fallback, logoPreview: fallback.branding.logo_url }
}

export function saveDemoProfile(tenantId: string, profile: ClinicProfile, logoPreview: string | null, storage: DemoStorage = localStorage) {
  storage.setItem(key(tenantId), JSON.stringify({ profile: profileUpdate(profileDraft(profile)), logoPreview }))
}

export function localLogoPreview(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(new Error('Could not read the image.'))
    reader.readAsDataURL(file)
  })
}
