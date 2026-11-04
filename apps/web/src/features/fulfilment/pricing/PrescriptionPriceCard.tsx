import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import type { Prescription, Prices } from '@/features/fulfilment/api/pricing'
import { pricePath, request } from '@/features/fulfilment/api/pricing'
import { prescriptionPrices } from '@/features/fulfilment/pricing/clinicMedicineQueries'
import { MedicationCorrectionEditor } from '@/features/fulfilment/pricing/MedicationCorrectionEditor'
import { decimal, minorUnits } from '@/features/fulfilment/pricing/money'
import { appointmentDetail } from '@/features/scheduling/api'
import { ApiError } from '@/lib/api'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { useState } from 'react'

export function PrescriptionPriceCard({
  prescription,
  tenantId,
  token,
}: {
  prescription: Prescription
  tenantId: string
  token: string
}) {
  const priceQuery = prescriptionPrices(
    tenantId,
    token,
    prescription.prescription_id,
  )
  const query = useQuery(priceQuery)
  const cache = useQueryClient()
  const appointment = useQuery({
    queryKey: ['pricing-patient', token, prescription.appointment_id],
    queryFn: ({ signal }) =>
      appointmentDetail(prescription.appointment_id, signal),
    retry: false,
    gcTime: 0,
  })
  return (
    <details
      className="group rounded-2xl border-2 border-amber-500 bg-white p-5"
      aria-label={`Prescription ${prescription.prescription_id.slice(-8)}`}
    >
      <summary className="flex cursor-pointer list-none items-start justify-between gap-4 rounded focus-visible:outline-2 focus-visible:outline-offset-4 [&::-webkit-details-marker]:hidden">
        <div className="min-w-0">
          <h2 className="font-semibold">
            Prescription {prescription.prescription_id.slice(-8)}
          </h2>
          <p className="mt-2 text-sm font-medium">
            {appointment.data?.patient_name ||
              `Patient ${prescription.patient_id.slice(-8)}`}
          </p>
          <p className="mt-1 text-xs text-slate-600">
            Prescription {prescription.prescription_id.slice(-8)} ·{' '}
            {new Intl.DateTimeFormat('en-SG', {
              timeZone: 'Asia/Singapore',
              dateStyle: 'medium',
            }).format(new Date(prescription.created_at))}
          </p>
          <p className="mt-1 text-sm text-slate-600">
            {prescription.items.map((item) => item.display_name).join(', ')}
          </p>
        </div>
        <ChevronDown
          aria-hidden="true"
          size={20}
          className="mt-1 shrink-0 text-slate-500 transition-transform group-open:rotate-180"
        />
      </summary>
      <div className="mt-4 space-y-4">
        <MedicationCorrectionEditor
          tenantId={tenantId}
          prescriptionId={prescription.prescription_id}
          token={token}
          disabled={query.data?.locked !== false}
        />
        <section
          className="space-y-4 rounded-xl border p-4"
          aria-label="Medication pricing"
        >
          <h3 className="font-semibold">Medication pricing</h3>
          {query.isPending ? (
            <LoadingState message="Loading prescription prices..." />
          ) : query.isError ? (
            <ErrorState
              message="Could not load prices."
              onRetry={() => void query.refetch()}
            />
          ) : (
            <PriceEditor
              prescription={prescription}
              tenantId={tenantId}
              initial={query.data}
              onSaved={async (prices) => {
                await cache.cancelQueries({ queryKey: priceQuery.queryKey })
                cache.setQueryData(priceQuery.queryKey, prices)
              }}
            />
          )}
        </section>
      </div>
    </details>
  )
}

function PriceEditor({
  prescription,
  tenantId,
  initial: saved,
  onSaved,
}: {
  prescription: Prescription
  tenantId: string
  initial: Prices
  onSaved: (prices: Prices) => Promise<void>
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      prescription.items.map((line) => {
        const price = saved.items.find(
          (item) => item.prescription_item_id === line.prescription_item_id,
        )?.unit_price.amount_minor
        return [
          line.prescription_item_id,
          price === undefined ? '' : decimal(price),
        ]
      }),
    ),
  )
  const amounts = prescription.items.map((line) =>
    minorUnits(values[line.prescription_item_id] ?? ''),
  )
  const total = prescription.items.reduce(
    (sum, line, index) => sum + (amounts[index] ?? 0) * line.quantity,
    0,
  )
  const valid =
    amounts.every((amount) => amount !== null) && Number.isSafeInteger(total)
  const dirty = prescription.items.some(
    (line, index) =>
      amounts[index] !==
      saved.items.find(
        (item) => item.prescription_item_id === line.prescription_item_id,
      )?.unit_price.amount_minor,
  )
  const mutation = useMutation({
    mutationFn: async () =>
      (
        await request(pricePath(tenantId, prescription.prescription_id), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            patient_id: prescription.patient_id,
            items: prescription.items.map((line, index) => ({
              prescription_item_id: line.prescription_item_id,
              unit_price: { amount_minor: amounts[index], currency: 'SGD' },
            })),
          }),
        })
      ).json() as Promise<Prices>,
    onSuccess: onSaved,
    retry: false,
    gcTime: 0,
  })
  return (
    <form
      className="space-y-4"
      aria-label={`Prices for prescription ${prescription.prescription_id.slice(-8)}`}
      onSubmit={(event) => {
        event.preventDefault()
        if (valid && dirty && !saved.locked && !mutation.isPending)
          mutation.mutate()
      }}
    >
      {saved.locked && (
        <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
          Prices are locked because the patient has opened a medicine order.
        </p>
      )}
      <fieldset
        className="space-y-4"
        disabled={saved.locked || mutation.isPending}
      >
        {prescription.items.map((line, index) => (
          <div
            key={line.prescription_item_id}
            className="space-y-2 rounded-lg border p-4"
          >
            <p className="text-sm font-medium">{line.display_name}</p>
            <p className="text-sm text-slate-600">Quantity: {line.quantity}</p>
            <label className="flex flex-col gap-2 text-sm">
              Unit price for {line.display_name} (SGD)
              <input
                className="rounded-lg border p-3"
                required
                inputMode="decimal"
                pattern="[0-9]+(\.[0-9]{1,2})?"
                placeholder="0.00"
                value={values[line.prescription_item_id] ?? ''}
                onChange={(event) =>
                  setValues({
                    ...values,
                    [line.prescription_item_id]: event.target.value,
                  })
                }
              />
            </label>
            {amounts[index] !== null &&
              Number.isSafeInteger(amounts[index]! * line.quantity) && (
                <p className="text-xs text-slate-600">
                  Line total: SGD {decimal(amounts[index]! * line.quantity)}
                </p>
              )}
          </div>
        ))}
      </fieldset>
      <p className="text-sm font-medium">
        Medication total:{' '}
        {valid ? `SGD ${decimal(total)}` : 'Enter all medication prices'}
      </p>
      {!saved.locked && (
        <Button
          className="h-10 px-4"
          disabled={!valid || !dirty || mutation.isPending}
        >
          {mutation.isPending ? 'Saving prices…' : 'Save prescription prices'}
        </Button>
      )}
      {mutation.isSuccess && !dirty && (
        <p role="status" className="text-sm text-teal-800">
          Prices saved for this prescription.
        </p>
      )}
      {mutation.isError && (
        <ErrorState
          message={
            mutation.error instanceof ApiError &&
            mutation.error.code === 'prescription_price_locked'
              ? 'The patient has already opened an order. Reload to see the locked prices.'
              : 'Could not save prices. Check clinic access and retry.'
          }
        />
      )}
    </form>
  )
}
