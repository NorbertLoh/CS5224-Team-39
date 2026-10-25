import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { PrescriptionItemFields } from './PrescriptionItemFields'
import { PrescriptionDetails } from './PrescriptionDetails'
import { savePrescription, issuePrescription, recordsError } from './api'
import { prescriptionItems, validItems } from './types'
import type { Prescription, PrescriptionInput } from './types'
import { ErrorState } from '../../components/ErrorState'
import { Pill, Plus } from 'lucide-react'
import { Button } from '../../components/ui/button'
import { useDraftAutosave } from './useDraftAutosave'
import {
  useRecordFormState,
  type RecordFormStateChange,
} from './useRecordFormState'

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
  const accept = (result: Prescription) => {
    setSaved(result)
    setItems(prescriptionItems(result.items))
  }
  const save = useMutation({
    mutationFn: () =>
      savePrescription(appointmentId, saved?.prescription_id, items, tenantId),
    onSuccess: accept,
    onError: onFailure,
    retry: false,
    gcTime: 0,
  })
  const issue = useMutation({
    mutationFn: () => issuePrescription(saved!.prescription_id),
    onSuccess: accept,
    onError: onFailure,
    retry: false,
    gcTime: 0,
  })
  const busy = save.isPending || issue.isPending
  const dirty =
    JSON.stringify(prescriptionItems(items)) !==
    JSON.stringify(prescriptionItems(saved?.items ?? []))
  const valid = validItems(items)
  useRecordFormState(dirty, busy, onStateChange)
  const writable = editable && !locked && !busy
  useDraftAutosave(
    writable && valid && dirty && !save.isError && !issue.isError,
    JSON.stringify(items),
    save.mutate,
  )
  const changeItems = (next: PrescriptionInput[]) => {
    setItems(next)
    save.reset()
    issue.reset()
  }
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
        Complete each medication to autosave the draft. Issue the prescription
        when ready. The clinic admin sets prices before checkout.
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
                changeItems([
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
                  changeItems(
                    items.map((current, position) =>
                      position === index ? { ...current, ...change } : current,
                    ),
                  )
                }
                onRemove={() =>
                  changeItems(items.filter((_, position) => position !== index))
                }
              />
            ))}
            <div className="flex flex-wrap gap-3">
              <Button
                className="h-10 px-4"
                type="button"
                disabled={!saved || dirty || !valid}
                onClick={() => {
                  if (writable && saved && !dirty && valid) issue.mutate()
                }}
              >
                {issue.isPending ? 'Issuing...' : 'Issue prescription'}
              </Button>
            </div>
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
      {issue.isSuccess && (
        <p role="status">Prescription issued. Its content is now locked.</p>
      )}
      {(save.isError || issue.isError) && (
        <ErrorState message={recordsError(save.error ?? issue.error)} />
      )}
    </form>
  )
}
