import { Button } from '@/components/ui/button'
import { request } from '@/features/fulfilment/api/pricing'
import { registerMedication } from '@/features/records/api'
import type { Prescription } from '@/features/records/types'
import { ApiError } from '@/lib/api'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

export function MedicationCorrectionEditor({
  tenantId,
  prescriptionId,
  token,
  disabled = false,
}: {
  tenantId: string
  prescriptionId: string
  token: string
  disabled?: boolean
}) {
  const [editing, setEditing] = useState(false)
  const path = `/clinical-records/clinics/${encodeURIComponent(tenantId)}/prescriptions/${encodeURIComponent(prescriptionId)}`
  const query = useQuery({
    queryKey: [
      'clinic-prescription-correction',
      token,
      tenantId,
      prescriptionId,
    ],
    queryFn: async ({ signal }) =>
      (
        await request(path + '/correction', { signal })
      ).json() as Promise<Prescription>,
    enabled: editing && !disabled,
    retry: false,
    gcTime: 0,
  })
  if (!editing || disabled)
    return (
      <div className="space-y-2">
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => setEditing(true)}
        >
          Add / edit medications
        </Button>
        {disabled && (
          <p className="text-sm text-slate-600">
            Corrections are available only on active unpaid orders before
            checkout or preparation.
          </p>
        )}
      </div>
    )
  return (
    <section
      className="space-y-4 rounded-xl border border-teal-200 bg-teal-50/30 p-4"
      aria-label="Correct prescription medications"
    >
      <h4 className="font-semibold">Correct prescription medications</h4>
      {query.isPending ? (
        <p role="status">Loading saved medications...</p>
      ) : query.isError ? (
        <p role="alert">
          Could not load the prescription.{' '}
          <button
            type="button"
            className="underline"
            onClick={() => void query.refetch()}
          >
            Retry
          </button>
        </p>
      ) : (
        <CorrectionForm
          key={prescriptionId}
          prescription={query.data}
          path={path}
          tenantId={tenantId}
          onClose={() => setEditing(false)}
        />
      )}
    </section>
  )
}

function CorrectionForm({
  prescription,
  path,
  tenantId,
  onClose,
}: {
  prescription: Prescription
  path: string
  tenantId: string
  onClose: () => void
}) {
  const cache = useQueryClient()
  const [items, setItems] = useState(() =>
    prescription.items.map((item) => ({
      ...item,
      key: item.prescription_item_id,
    })),
  )
  const [reason, setReason] = useState('')
  const valid =
    reason.trim().length > 0 &&
    items.every(
      (item) =>
        item.display_name.trim() &&
        item.instructions.trim() &&
        Number.isSafeInteger(item.quantity) &&
        item.quantity > 0 &&
        item.quantity <= 10000,
    )
  const mutation = useMutation({
    mutationFn: async () => {
      const resolved = []
      for (const item of items) {
        const medication = item.medication_id
          ? null
          : await registerMedication(tenantId, item.display_name)
        resolved.push({
          medication_id: item.medication_id || medication!.medication_id,
          quantity: item.quantity,
          instructions: item.instructions,
        })
      }
      return (
        await request(path + '/corrections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: reason.trim(), items: resolved }),
        })
      ).json()
    },
    retry: false,
    onSuccess: async () => {
      await Promise.all(
        [
          'clinic-prescription-pricing',
          'prescription-prices',
          'fulfilment',
          'records',
          'documents',
        ].map((key) => cache.invalidateQueries({ queryKey: [key] })),
      )
      onClose()
    },
  })
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        if (valid && !mutation.isPending) mutation.mutate()
      }}
    >
      <p className="text-sm text-slate-600">
        Saving withdraws the original and issues a corrected prescription. Any
        untouched unpaid order is cancelled; the corrected medicines need fresh
        pricing and a new order. Previous records remain in the history.
      </p>
      <fieldset disabled={mutation.isPending} className="space-y-4">
        {items.map((item, index) => (
          <div
            key={item.key}
            className="space-y-3 rounded-lg border bg-white p-4"
          >
            <label className="block text-sm">
              Medication name
              <input
                aria-label={`Medication ${index + 1} name`}
                required
                maxLength={200}
                className="mt-1 w-full rounded border p-2"
                value={item.display_name}
                onChange={(event) =>
                  setItems(
                    items.map((row, position) =>
                      position === index
                        ? {
                            ...row,
                            display_name: event.target.value,
                            medication_id: '',
                          }
                        : row,
                    ),
                  )
                }
              />
            </label>
            <label className="block text-sm">
              Quantity
              <input
                aria-label={`Medication ${index + 1} quantity`}
                type="number"
                required
                min={1}
                max={10000}
                step={1}
                className="mt-1 w-full rounded border p-2"
                value={item.quantity || ''}
                onChange={(event) =>
                  setItems(
                    items.map((row, position) =>
                      position === index
                        ? { ...row, quantity: Number(event.target.value) }
                        : row,
                    ),
                  )
                }
              />
            </label>
            <label className="block text-sm">
              Instructions
              <textarea
                aria-label={`Medication ${index + 1} instructions`}
                required
                maxLength={20000}
                className="mt-1 w-full rounded border p-2"
                value={item.instructions}
                onChange={(event) =>
                  setItems(
                    items.map((row, position) =>
                      position === index
                        ? { ...row, instructions: event.target.value }
                        : row,
                    ),
                  )
                }
              />
            </label>
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                setItems(items.filter((_, position) => position !== index))
              }
            >
              Remove medication {index + 1}
            </Button>
          </div>
        ))}
        {!items.length && (
          <p className="text-sm">
            No medications remain. Saving will withdraw this prescription.
          </p>
        )}
        <Button
          type="button"
          variant="outline"
          disabled={items.length >= 100}
          onClick={() =>
            setItems([
              ...items,
              {
                key: crypto.randomUUID(),
                prescription_item_id: '',
                medication_id: '',
                display_name: '',
                quantity: 1,
                instructions: '',
              },
            ])
          }
        >
          Add medication
        </Button>
        <label className="block text-sm">
          Correction reason
          <input
            required
            maxLength={500}
            className="mt-1 w-full rounded border p-2"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <div className="flex gap-3">
          <Button disabled={!valid}>
            {mutation.isPending
              ? 'Saving correction...'
              : 'Save prescription correction'}
          </Button>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel correction
          </Button>
        </div>
      </fieldset>
      {mutation.isError && (
        <p role="alert" className="text-sm text-red-700">
          {mutation.error instanceof ApiError &&
          mutation.error.code === 'prescription_correction_locked'
            ? 'This order has entered checkout or preparation and cannot be corrected here.'
            : 'Could not complete the correction. Keep these edits and retry; refresh if the prescription was already corrected.'}
        </p>
      )}
    </form>
  )
}
