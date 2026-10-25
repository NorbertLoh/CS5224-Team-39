import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { catalogue, priceMedication, recordsError } from '../records/api'
import type { Medication } from '../records/types'
import { Button } from '../../components/ui/button'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

function minorUnits(value: string): number | null {
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(value.trim())
  if (!match) return null
  const amount =
    Number(match[1]) * 100 + Number((match[2] ?? '').padEnd(2, '0'))
  return Number.isSafeInteger(amount) && amount >= 0 ? amount : null
}

export function ClinicMedicationCatalogue({
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
      aria-label="Medication pricing"
    >
      <div>
        <h2 className="text-xl font-semibold">Medications &amp; prices</h2>
        <p className="mt-2 text-sm text-slate-600">
          Doctors can type any medication name. Set its dispensing unit and
          price here before patients can order it.
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
      <CataloguePrices
        key={`${token}:${selected}`}
        tenantId={selected}
        token={token}
      />
    </section>
  )
}

function CataloguePrices({
  tenantId,
  token,
}: {
  tenantId: string
  token: string
}) {
  const query = useQuery({
    queryKey: ['admin-catalogue', token, tenantId],
    queryFn: ({ signal }) => catalogue(tenantId, signal),
    retry: false,
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
  if (query.isPending)
    return <LoadingState message="Loading medication prices..." />
  if (query.isError)
    return (
      <ErrorState
        message={recordsError(query.error)}
        onRetry={() => void query.refetch()}
      />
    )
  const items = [...query.data].sort(
    (a, b) =>
      Number(a.unit_price !== null) - Number(b.unit_price !== null) ||
      a.display_name.localeCompare(b.display_name),
  )
  return (
    <div className="space-y-4">
      {!items.length && (
        <p className="text-sm text-slate-600">
          Medication names appear here when a doctor saves a prescription draft.
        </p>
      )}
      {items.map((item) => (
        <MedicationPrice
          key={item.medication_id}
          medication={item}
          tenantId={tenantId}
        />
      ))}
      <Button
        variant="outline"
        type="button"
        disabled={query.isFetching}
        onClick={() => void query.refetch()}
      >
        Refresh medications
      </Button>
    </div>
  )
}

function MedicationPrice({
  medication,
  tenantId,
}: {
  medication: Medication
  tenantId: string
}) {
  const [unit, setUnit] = useState(medication.unit_label)
  const [price, setPrice] = useState(
    medication.unit_price
      ? `${Math.trunc(medication.unit_price.amount_minor / 100)}.${String(medication.unit_price.amount_minor % 100).padStart(2, '0')}`
      : '',
  )
  const [saved, setSaved] = useState(medication)
  const mutation = useMutation({
    mutationFn: () =>
      priceMedication(tenantId, saved, minorUnits(price)!, unit),
    onSuccess: setSaved,
    retry: false,
    gcTime: 0,
  })
  const amount = minorUnits(price)
  const dirty =
    amount !== saved.unit_price?.amount_minor ||
    unit.trim() !== saved.unit_label
  return (
    <form
      className="space-y-4 rounded-xl border bg-white p-5"
      onSubmit={(event) => {
        event.preventDefault()
        if (amount !== null && unit.trim() && dirty && !mutation.isPending)
          mutation.mutate()
      }}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-semibold">{medication.display_name}</h3>
        <span
          className={`rounded-full px-3 py-1 text-xs ${saved.unit_price === null ? 'bg-amber-50 text-amber-900' : 'bg-teal-50 text-teal-900'}`}
        >
          {saved.unit_price === null ? 'Price needed' : 'Priced'}
        </span>
      </div>
      <fieldset
        className="grid gap-4 sm:grid-cols-2"
        disabled={mutation.isPending}
      >
        <label className="flex flex-col gap-2 text-sm">
          Dispensing unit
          <input
            className="rounded-lg border p-3"
            required
            maxLength={80}
            value={unit}
            onChange={(event) => setUnit(event.target.value)}
            placeholder="e.g. tablet, bottle"
          />
        </label>
        <label className="flex flex-col gap-2 text-sm">
          Unit price (SGD)
          <input
            className="rounded-lg border p-3"
            required
            inputMode="decimal"
            pattern="[0-9]+(\.[0-9]{1,2})?"
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            placeholder="0.00"
          />
        </label>
      </fieldset>
      <Button
        className="h-10 px-4"
        disabled={
          !dirty || amount === null || !unit.trim() || mutation.isPending
        }
      >
        {mutation.isPending ? 'Saving price…' : 'Save price'}
      </Button>
      {mutation.isSuccess && !dirty && (
        <p role="status" className="text-sm text-teal-800">
          Price saved.
        </p>
      )}
      {mutation.isError && (
        <ErrorState message="Could not save the price. Check your clinic access and try again." />
      )}
    </form>
  )
}
