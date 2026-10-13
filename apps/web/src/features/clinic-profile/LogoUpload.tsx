import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { readLogo, removeLogo, uploadLogo, validateLogoFile } from './logo-api'

export function LogoUpload({ tenantId, preview, onChange }: {
  tenantId: string
  preview: string | null
  onChange: (url: string | null, preview: string | null) => void
}) {
  const [busy, setBusy] = useState(true)
  const [notice, setNotice] = useState('')
  const [failedPreview, setFailedPreview] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    readLogo(tenantId).then(result => {
      if (!cancelled) onChange(result.url, result.preview)
      else if (result.preview?.startsWith('blob:')) URL.revokeObjectURL(result.preview)
    }).catch(() => {
      if (!cancelled) setNotice('Sign in with clinic-admin access to load or change the stored logo.')
    }).finally(() => { if (!cancelled) setBusy(false) })
    return () => { cancelled = true }
  }, [tenantId, onChange])

  useEffect(() => () => {
    if (preview?.startsWith('blob:')) URL.revokeObjectURL(preview)
  }, [preview])

  async function select(file: File | undefined) {
    if (!file) return
    const error = validateLogoFile(file)
    if (error) { setNotice(error); return }
    setBusy(true)
    setNotice('Uploading logo…')
    try {
      const result = await uploadLogo(tenantId, file)
      onChange(result.url, result.preview)
      setNotice('Logo saved. The previous image was replaced.')
    } catch {
      setNotice('Logo upload failed. Check the image and your sign-in, then try again.')
    } finally { setBusy(false) }
  }

  async function remove() {
    setBusy(true)
    try {
      await removeLogo(tenantId)
      onChange(null, null)
      setNotice('Logo removed from storage.')
    } catch { setNotice('Could not remove the logo. Try again.') }
    finally { setBusy(false) }
  }

  return (
    <div>
      <input id="profile-logoUrl" type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} aria-describedby="logo-help logo-status" onChange={event => {
        const file = event.target.files?.[0]
        event.target.value = ''
        void select(file)
      }} className="w-full min-w-0 rounded-lg border border-slate-300 p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:font-medium" />
      {preview && (
        <div className="mt-3 flex size-32 items-center justify-center rounded-lg border border-slate-200 bg-white p-2">
          {failedPreview === preview ? <p className="text-center text-xs text-slate-500">Logo preview unavailable.</p> : (
            <img key={preview} src={preview} alt="Current clinic logo" width={128} height={128} className="size-full object-contain" onError={() => setFailedPreview(preview)} />
          )}
        </div>
      )}
      <p id="logo-help" className="mt-2 text-xs text-slate-500">PNG, JPEG or WebP, up to 2 MB and 4 megapixels. Logo changes save immediately.</p>
      {preview && <Button type="button" variant="outline" disabled={busy} onClick={() => void remove()} className="mt-3">Remove logo</Button>}
      <p id="logo-status" role="status" className="mt-2 text-sm text-slate-600">{notice}</p>
    </div>
  )
}
