import {
  PickupLocationFields,
  emptyPickupLocation,
  type PickupLocation as Location,
} from '@/features/clinics/components/PickupLocationFields'
import { readSession } from '@/auth/session'
import { ErrorState } from '@/components/ErrorState'
import { clinicRequest } from '@/features/clinics/api'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useState } from 'react'

type Settings = { tenant_id: string; location: Location | null }

export function ClinicSettings({ tenantId }: { tenantId: string }) {
  const path = `/clinics/${encodeURIComponent(tenantId)}/location`
  const query = useQuery({
    queryKey: ['clinic-location', readSession()?.accessToken, tenantId],
    queryFn: async () =>
      (await clinicRequest(path, {}, true)).json() as Promise<Settings>,
    retry: false,
  })
  return (
    <main className="mx-auto max-w-3xl space-y-6 px-6 py-10">
      <h1 className="text-3xl font-semibold">Clinic settings</h1>
      {query.isPending ? (
        <p role="status">Loading clinic settings...</p>
      ) : query.isError ? (
        <ErrorState
          message="Could not load clinic settings."
          onRetry={() => void query.refetch()}
        />
      ) : (
        <LocationEditor path={path} initial={query.data.location} />
      )}
    </main>
  )
}

function LocationEditor({
  path,
  initial,
}: {
  path: string
  initial: Location | null
}) {
  const [location, setLocation] = useState<Location>(
    initial
      ? {
          ...initial,
          pickup_contact: initial.pickup_contact ?? { name: '', phone: '' },
        }
      : emptyPickupLocation(),
  )
  const [saved, setSaved] = useState(initial)
  const dirty = JSON.stringify(location) !== JSON.stringify(saved)
  const mutation = useMutation({
    mutationFn: async () =>
      (
        await clinicRequest(
          path,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(location),
          },
          true,
        )
      ).json() as Promise<Settings>,
    retry: false,
    onSuccess: (result) => {
      setSaved(result.location)
      if (result.location) setLocation(result.location)
    },
  })
  return (
    <form
      className="space-y-5 rounded-xl border bg-white p-6"
      onSubmit={(event) => {
        event.preventDefault()
        mutation.mutate()
      }}
    >
      <div>
        <h2 className="text-xl font-semibold">Medicine pickup location</h2>
        <p className="mt-2 text-sm text-slate-600">
          Delivery fees and courier pickup use this clinic location. Changes
          apply to new delivery quotes.
        </p>
      </div>
      <fieldset disabled={mutation.isPending} className="space-y-4">
        <PickupLocationFields location={location} setLocation={setLocation} />
        <button
          disabled={!dirty}
          className="rounded-lg bg-slate-900 px-5 py-3 font-medium text-white disabled:opacity-50"
        >
          {mutation.isPending
            ? 'Saving pickup details...'
            : 'Save pickup details'}
        </button>
      </fieldset>
      {mutation.isSuccess && !dirty && (
        <p role="status" className="text-sm text-emerald-800">
          Pickup details saved.
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="text-sm text-red-700">
          Could not save the pickup details. Check the contact name, Singapore
          phone number, address, postcode and coordinates, then try again.
        </p>
      )}
    </form>
  )
}
