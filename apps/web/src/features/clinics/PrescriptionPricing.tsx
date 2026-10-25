import { useState } from 'react'
import { useInfiniteQuery, useMutation, useQuery } from '@tanstack/react-query'
import { apiFetch, ApiError } from '../../lib/api'
import { accessToken } from './api'
import { appointmentDetail } from '../scheduling/api'
import { Button } from '../../components/ui/button'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

type Money = { amount_minor: number; currency: 'SGD' }
type Line = {
  prescription_item_id: string
  display_name: string
  quantity: number
}
type Prescription = {
  prescription_id: string
  appointment_id: string
  patient_id: string
  created_at: string
  items: Line[]
}
type Prices = {
  prescription_id: string
  locked: boolean
  items: { prescription_item_id: string; unit_price: Money }[]
}
async function request(path: string, init: RequestInit = {}) {
  return apiFetch(path, {
    ...init,
    accessToken: await accessToken(),
    signal: init.signal ?? AbortSignal.timeout(15000),
  })
}
function pricePath(tenantId: string, prescriptionId: string) {
  return `/fulfilment/clinics/${encodeURIComponent(tenantId)}/prescriptions/${encodeURIComponent(prescriptionId)}/prices`
}
function minorUnits(value: string): number | null {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
  if (!match) return null
  const amount =
    Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'))
  return Number.isSafeInteger(amount) && amount >= 0 ? amount : null
}
function decimal(minor: number) {
  return `${Math.trunc(minor / 100)}.${String(minor % 100).padStart(2, '0')}`
}

export function PrescriptionPricing({
  clinics,
  token,
}: {
  clinics: { tenant_id: string; name: string }[]
  token: string
}) {
  const [selected, setSelected] = useState(clinics[0]?.tenant_id ?? '')
  if (!clinics.length) return null
  return (
    <section
      className="mt-10 space-y-5 rounded-2xl border bg-slate-50/50 p-5 sm:p-6"
      aria-label="Prescription pricing"
    >
      <div>
        <h2 className="text-xl font-semibold">Prescription pricing</h2>
        <p className="mt-2 text-sm text-slate-600">
          Use your clinic’s own system as a reference. Enter prices for each
          issued prescription here; no catalogue maintenance is needed.
        </p>
      </div>
      <label className="flex flex-col gap-2 text-sm font-medium">
        Clinic
        <select
          className="rounded-lg border bg-white p-3"
          value={selected}
          onChange={(event) => setSelected(event.target.value)}
        >
          {clinics.map((clinic) => (
            <option key={clinic.tenant_id} value={clinic.tenant_id}>
              {clinic.name}
            </option>
          ))}
        </select>
      </label>
      <PricingQueue
        key={`${token}:${selected}`}
        tenantId={selected}
        token={token}
      />
    </section>
  )
}

function PricingQueue({
  tenantId,
  token,
}: {
  tenantId: string
  token: string
}) {
  const query = useInfiniteQuery({
    queryKey: ['clinic-prescription-pricing', token, tenantId],
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) =>
      (
        await request(
          `/clinical-records/clinics/${encodeURIComponent(tenantId)}/prescription-pricing${pageParam ? '?cursor=' + encodeURIComponent(pageParam) : ''}`,
          { signal },
        )
      ).json() as Promise<{
        items: Prescription[]
        next_cursor: string | null
      }>,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
  })
  if (query.isPending)
    return <LoadingState message="Loading issued prescriptions..." />
  const rows = query.data?.pages.flatMap((page) => page.items) ?? []
  return (
    <div className="space-y-4">
      {rows.map((row) => (
        <PrescriptionPrices
          key={row.prescription_id}
          prescription={row}
          tenantId={tenantId}
          token={token}
        />
      ))}
      {!rows.length && !query.isError && (
        <p className="text-sm text-slate-600">
          Issued prescriptions will appear here for pricing.
        </p>
      )}
      {query.isError && (
        <ErrorState
          message="Could not load prescriptions. Check your clinic access and retry."
          onRetry={() => void query.refetch()}
        />
      )}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="outline"
          type="button"
          disabled={query.isFetching}
          onClick={() => void query.refetch()}
        >
          Refresh prescriptions
        </Button>
        {query.hasNextPage && (
          <Button
            variant="outline"
            type="button"
            disabled={query.isFetching}
            onClick={() => void query.fetchNextPage()}
          >
            Load older prescriptions
          </Button>
        )}
      </div>
    </div>
  )
}

function PrescriptionPrices({
  prescription,
  tenantId,
  token,
}: {
  prescription: Prescription
  tenantId: string
  token: string
}) {
  const query = useQuery({
    queryKey: [
      'prescription-prices',
      token,
      tenantId,
      prescription.prescription_id,
    ],
    queryFn: async ({ signal }) =>
      (
        await request(pricePath(tenantId, prescription.prescription_id), {
          signal,
        })
      ).json() as Promise<Prices>,
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  const appointment = useQuery({
    queryKey: ['pricing-patient', token, prescription.appointment_id],
    queryFn: ({ signal }) =>
      appointmentDetail(prescription.appointment_id, signal),
    retry: false,
    gcTime: 0,
  })
  return (
    <article className="space-y-4 rounded-xl border bg-white p-5">
      <div>
        <h3 className="font-semibold">
          {appointment.data?.patient_name ||
            `Patient ${prescription.patient_id.slice(-8)}`}
        </h3>
        <p className="mt-1 text-xs text-slate-600">
          Prescription {prescription.prescription_id.slice(-8)} ·{' '}
          {new Intl.DateTimeFormat('en-SG', {
            timeZone: 'Asia/Singapore',
            dateStyle: 'medium',
          }).format(new Date(prescription.created_at))}
        </p>
      </div>
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
        />
      )}
    </article>
  )
}

function PriceEditor({
  prescription,
  tenantId,
  initial,
}: {
  prescription: Prescription
  tenantId: string
  initial: Prices
}) {
  const [saved, setSaved] = useState(initial)
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      prescription.items.map((line) => {
        const price = initial.items.find(
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
    onSuccess: setSaved,
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
