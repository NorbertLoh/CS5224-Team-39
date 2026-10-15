import { useState } from 'react'
import { PrescriptionItemFields } from './PrescriptionItemFields'
import { draftPrescription, validItems } from './fixtures'
import type { PreviewPrescription, PrescriptionInput } from './fixtures'

const button = 'rounded border px-4 py-2 disabled:opacity-50'

export function PrescriptionEditor({
  onStatus,
}: {
  onStatus: (message: string) => void
}) {
  const [items, setItems] = useState<PrescriptionInput[]>([])
  const [saved, setSaved] = useState<PreviewPrescription | null>(null)
  const issued = saved?.status === 'issued'
  const dirty =
    JSON.stringify(
      items.map(({ display_name, quantity, instructions }) => ({
        display_name: display_name.trim(),
        quantity,
        instructions: instructions.trim(),
      })),
    ) !==
    JSON.stringify(
      saved?.items.map(({ display_name, quantity, instructions }) => ({
        display_name,
        quantity,
        instructions,
      })) ?? [],
    )
  const updateItem = (index: number, change: Partial<PrescriptionInput>) => {
    setItems((current) =>
      current.map((item, i) => (i === index ? { ...item, ...change } : item)),
    )
    onStatus('')
  }
  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        setSaved(draftPrescription(items))
        onStatus('Prescription draft saved in this preview.')
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold">
          Prescription · {saved?.status ?? 'new'}
        </h3>
        {!issued && (
          <button
            className={button}
            type="button"
            onClick={() =>
              setItems((current) => [
                ...current,
                { display_name: '', quantity: 1, instructions: '' },
              ])
            }
          >
            Add medication
          </button>
        )}
      </div>
      {!items.length && (
        <p className="text-sm text-slate-600">
          No medications added. Add a medication and type its name to start.
        </p>
      )}
      {items.map((item, index) => (
        <PrescriptionItemFields
          key={index}
          item={item}
          index={index}
          issued={issued}
          onChange={(change) => updateItem(index, change)}
          onRemove={() =>
            setItems((current) => current.filter((_, i) => i !== index))
          }
        />
      ))}
      {!issued && (
        <div className="flex flex-wrap gap-3">
          <button className={button} disabled={!validItems(items) || !dirty}>
            Save preview draft
          </button>
          <button
            className={button}
            type="button"
            disabled={!saved || dirty || !validItems(items)}
            onClick={() => {
              setSaved(
                (current) =>
                  current && {
                    ...current,
                    status: 'issued',
                    issued_at: new Date().toISOString(),
                    updated_at: new Date().toISOString(),
                  },
              )
              onStatus(
                'Prescription issued in this preview. Its content is now locked.',
              )
            }}
          >
            Issue preview prescription
          </button>
        </div>
      )}
      {issued && (
        <p className="text-sm">
          Issued prescription content is locked. Reload to reset the synthetic
          preview.
        </p>
      )}
    </form>
  )
}
