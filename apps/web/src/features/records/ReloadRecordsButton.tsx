import { useRef, useState } from 'react'
import { AlertDialog } from 'radix-ui'
import { RefreshCw } from 'lucide-react'
import { Button } from '../../components/ui/button'

export function ReloadRecordsButton({
  dirty,
  busy,
  onReload,
}: {
  dirty: boolean
  busy: boolean
  onReload: () => void
}) {
  const [confirm, setConfirm] = useState(false)
  const reloadButton = useRef<HTMLButtonElement>(null)
  return (
    <AlertDialog.Root open={confirm} onOpenChange={setConfirm}>
      <Button
        ref={reloadButton}
        type="button"
        variant="outline"
        className="h-9"
        disabled={busy}
        onClick={() => (dirty ? setConfirm(true) : onReload())}
      >
        <RefreshCw aria-hidden="true" /> Reload saved records
      </Button>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-50 bg-slate-950/40" />
        <AlertDialog.Content
          onCloseAutoFocus={(event) => {
            event.preventDefault()
            reloadButton.current?.focus()
          }}
          className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-2xl bg-white p-6 shadow-xl"
        >
          <AlertDialog.Title className="text-lg font-semibold">
            Discard unsaved changes?
          </AlertDialog.Title>
          <AlertDialog.Description className="text-sm leading-6 text-slate-600">
            Reloading replaces your unsaved note, prescription and MC edits with
            the last saved records. Saved records stay intact.
          </AlertDialog.Description>
          <div className="flex flex-wrap justify-end gap-3">
            <AlertDialog.Cancel asChild>
              <Button variant="outline" className="h-10">
                Keep editing
              </Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button
                variant="destructive"
                className="h-10"
                disabled={busy}
                onClick={onReload}
              >
                Discard and reload
              </Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  )
}
