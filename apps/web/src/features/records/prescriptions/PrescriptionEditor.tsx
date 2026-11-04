import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { recordsError, savePrescription } from '@/features/records/api'
import {
  prescriptionItems,
  validItems,
} from '@/features/records/domain/prescriptions'
import { useDraftAutosave } from '@/features/records/hooks/useDraftAutosave'
import {
  useRecordFormState,
  type RecordFormStateChange,
} from '@/features/records/hooks/useRecordFormState'
import { PrescriptionDetails } from '@/features/records/prescriptions/PrescriptionDetails'
import { PrescriptionItemFields } from '@/features/records/prescriptions/PrescriptionItemFields'
import type { Prescription, PrescriptionInput } from '@/features/records/types'
import { useMutation } from '@tanstack/react-query'
import { Pill, Plus } from 'lucide-react'
import { useCallback, useState } from 'react'

function draftKey(items: PrescriptionInput[]) {
  return JSON.stringify(
    prescriptionItems(items)
      .map((item) => ({
        name:
          item.medication_id || item.display_name?.trim().toLowerCase() || '',
        quantity: item.quantity,
        instructions: item.instructions,
      }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  )
}

export function PrescriptionEditor({
  appointmentId,
  tenantId,
  prescription,
  editable,
  onFailure,
  onStateChange,
}: {
  appointmentId: string
  tenantId: string
  token: string
  prescription: Prescription | null
  editable: boolean
  onFailure: () => void
  onStateChange?: RecordFormStateChange
}) {
  const [saved, setSaved] = useState(prescription)
  const [items, setItems] = useState<PrescriptionInput[]>(
    prescriptionItems(prescription?.items ?? []),
  )
  const locked = Boolean(saved && saved.status !== 'draft')
  const save = useMutation({
    mutationFn: (submitted: PrescriptionInput[]) =>
      savePrescription(
        appointmentId,
        saved?.prescription_id,
        submitted,
        tenantId,
      ),
    onSuccess: (result) => {
      setSaved(result)
      // Merge identifiers without reordering rows or replacing visible input text.
      setItems((current) =>
        current.map((item) => {
          const matched = result.items.find(
            (line) =>
              line.display_name.trim().toLowerCase() ===
              item.display_name?.trim().toLowerCase(),
          )
          return matched
            ? { ...item, medication_id: matched.medication_id }
            : item
        }),
      )
    },
    onError: onFailure,
    retry: false,
    gcTime: 0,
  })
  const busy = save.isPending
  const dirty = draftKey(items) !== draftKey(saved?.items ?? [])
  const valid = validItems(items)
  useRecordFormState(dirty, busy, onStateChange)
  const writable = editable && !locked
  const queueSave = useCallback(
    () => save.mutate(prescriptionItems(items)),
    [save.mutate, items],
  )
  useDraftAutosave(
    writable && !save.isPending && valid && dirty && !save.isError,
    JSON.stringify(items),
    queueSave,
  )
  return (
    <form
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm"
      onSubmit={(event) => {
        event.preventDefault()
      }}
    >
      <div className="flex items-center gap-3">
        <span className="rounded-lg bg-teal-50 p-2 text-teal-800">
          <Pill aria-hidden="true" size={18} />
        </span>
        <h3 className="font-semibold">Prescription</h3>
        <span className="ml-auto rounded-full bg-slate-100 px-2 py-1 text-xs capitalize text-slate-600">
          {saved?.status ?? 'New'}
        </span>
      </div>
      <p className="text-sm text-slate-600">
        Complete each medication to autosave the draft. End consultation issues
        the saved prescription automatically. The clinic admin prices each
        medication before checkout.
      </p>
      {locked || !editable ? (
        <>
          {saved ? (
            <PrescriptionDetails prescription={saved} />
          ) : (
            <p>No prescription saved.</p>
          )}
          {locked && <p>Issued or voided prescription content is locked.</p>}
        </>
      ) : (
        <>
          <fieldset disabled={!writable} className="space-y-4">
            <Button
              variant="outline"
              className="h-10 px-4"
              type="button"
              disabled={items.length >= 100}
              onClick={() =>
                setItems([
                  ...items,
                  {
                    medication_id: '',
                    display_name: '',
                    quantity: 1,
                    instructions: '',
                  },
                ])
              }
            >
              <Plus aria-hidden="true" /> Add medication
            </Button>
            {!items.length && (
              <p className="text-sm text-slate-500">
                No medications added to this visit.
              </p>
            )}
            {items.map((item, index) => (
              <PrescriptionItemFields
                key={index}
                item={item}
                index={index}
                onChange={(change) =>
                  setItems(
                    items.map((current, position) =>
                      position === index ? { ...current, ...change } : current,
                    ),
                  )
                }
                onRemove={() =>
                  setItems(items.filter((_, position) => position !== index))
                }
              />
            ))}
          </fieldset>
          <p role="status" className="text-xs text-slate-600">
            {save.isError
              ? 'Draft not saved. Reload saved records to check the last outcome.'
              : save.isPending
                ? 'Saving prescription draft…'
                : dirty
                  ? valid
                    ? 'Waiting to autosave…'
                    : 'Complete medication, quantity and instructions for every item to autosave. Drafts require at least one item.'
                  : saved
                    ? 'Prescription draft saved.'
                    : 'Valid prescription drafts save automatically.'}
          </p>
        </>
      )}
      {save.isError && (
        <ErrorState message={recordsError(save.error)} />
      )}
    </form>
  )
}
