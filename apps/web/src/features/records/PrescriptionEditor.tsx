import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { PrescriptionItemFields } from './PrescriptionItemFields'
import { PrescriptionDetails } from './PrescriptionDetails'
import {
  catalogue,
  savePrescription,
  issuePrescription,
  recordsError,
} from './api'
import { prescriptionItems, validItems } from './types'
import type { Prescription, PrescriptionInput } from './types'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
const button = 'rounded border px-4 py-2 disabled:opacity-50'

export function PrescriptionEditor({
  appointmentId,
  tenantId,
  token,
  prescription,
  editable,
  onFailure,
}: {
  appointmentId: string
  tenantId: string
  token: string
  prescription: Prescription | null
  editable: boolean
  onFailure: () => void
}) {
  const [saved, setSaved] = useState(prescription)
  const [items, setItems] = useState<PrescriptionInput[]>(
    prescriptionItems(prescription?.items ?? []),
  )
  const locked = Boolean(saved && saved.status !== 'draft')
  const medications = useQuery({
    queryKey: ['records', 'catalogue', token, tenantId],
    queryFn: ({ signal }) => catalogue(tenantId, signal),
    enabled: editable && !locked,
    retry: false,
    gcTime: 0,
  })
  const accept = (result: Prescription) => {
    setSaved(result)
    setItems(prescriptionItems(result.items))
  }
  const save = useMutation({
    mutationFn: () =>
      savePrescription(appointmentId, saved?.prescription_id, items),
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
  const valid =
    validItems(items) &&
    items.every((item) =>
      medications.data?.some(
        (medication) => medication.medication_id === item.medication_id,
      ),
    )
  const writable = editable && !locked && medications.isSuccess && !busy
  const changeItems = (next: PrescriptionInput[]) => {
    setItems(next)
    save.reset()
    issue.reset()
  }
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (writable && valid && dirty) save.mutate()
      }}
    >
      <h3 className="font-semibold">Prescription · {saved?.status ?? 'new'}</h3>
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
          {medications.isPending && (
            <LoadingState message="Loading clinic medications..." />
          )}
          {medications.isError && (
            <ErrorState
              message={recordsError(medications.error)}
              onRetry={() => void medications.refetch()}
            />
          )}
          {medications.isSuccess && !medications.data.length && (
            <p role="status">
              No active medications in this clinic's catalogue.
            </p>
          )}
          <fieldset disabled={!writable} className="space-y-4">
            <button
              className={button}
              type="button"
              disabled={items.length >= 100}
              onClick={() =>
                changeItems([
                  ...items,
                  { medication_id: '', quantity: 1, instructions: '' },
                ])
              }
            >
              Add medication
            </button>
            {!items.length && <p>No medications added.</p>}
            {items.map((item, index) => (
              <PrescriptionItemFields
                key={index}
                item={item}
                index={index}
                medications={medications.data ?? []}
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
              <button className={button} disabled={!valid || !dirty}>
                {save.isPending ? 'Saving draft...' : 'Save draft'}
              </button>
              <button
                className={button}
                type="button"
                disabled={!saved || dirty || !valid}
                onClick={() => {
                  if (writable && saved && !dirty && valid) issue.mutate()
                }}
              >
                {issue.isPending ? 'Issuing...' : 'Issue prescription'}
              </button>
            </div>
          </fieldset>
          {dirty && (
            <p className="text-sm">Save draft changes before issuing.</p>
          )}
        </>
      )}
      {save.isSuccess && <p role="status">Prescription draft saved.</p>}
      {issue.isSuccess && (
        <p role="status">Prescription issued. Its content is now locked.</p>
      )}
      {(save.isError || issue.isError) && (
        <ErrorState message={recordsError(save.error ?? issue.error)} />
      )}
    </form>
  )
}
