import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { clinicRequest } from './api'
import { readSession } from '../../auth/session'
import { ErrorState } from '../../components/ErrorState'

type Location = {
  address_line: string
  postal_code: string
  country_code: 'SG'
  coordinates: { lat: string; lng: string }
  pickup_contact?: { name: string; phone: string } | null
}
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
      : {
          address_line: '',
          postal_code: '',
          country_code: 'SG',
          coordinates: { lat: '', lng: '' },
          pickup_contact: { name: '', phone: '' },
        },
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
        <h3 className="font-semibold">Pickup contact</h3>
        <p className="text-sm text-slate-600">
          The courier uses these details to contact the clinic for medicine
          pickup.
        </p>
        <label className="block text-sm font-medium">
          Pickup contact name
          <input
            required
            maxLength={100}
            className="mt-1 block w-full rounded-lg border p-3"
            autoComplete="name"
            value={location.pickup_contact?.name ?? ''}
            onChange={(event) =>
              setLocation({
                ...location,
                pickup_contact: {
                  name: event.target.value,
                  phone: location.pickup_contact?.phone ?? '',
                },
              })
            }
          />
        </label>
        <label className="block text-sm font-medium">
          Pickup phone number
          <input
            required
            type="tel"
            maxLength={24}
            className="mt-1 block w-full rounded-lg border p-3"
            autoComplete="tel"
            placeholder="e.g. +65 8123 4567"
            value={location.pickup_contact?.phone ?? ''}
            onChange={(event) =>
              setLocation({
                ...location,
                pickup_contact: {
                  name: location.pickup_contact?.name ?? '',
                  phone: event.target.value,
                },
              })
            }
          />
        </label>
        <p className="text-sm text-slate-600">
          Use an 8-digit Singapore number or include +65.
        </p>
        <h3 className="font-semibold">Pickup location</h3>
        <label className="block text-sm font-medium">
          Clinic pickup address
          <input
            required
            maxLength={300}
            className="mt-1 block w-full rounded-lg border p-3"
            autoComplete="street-address"
            value={location.address_line}
            onChange={(event) =>
              setLocation({ ...location, address_line: event.target.value })
            }
          />
        </label>
        <label className="block text-sm font-medium">
          Postal code
          <input
            required
            pattern="[0-9]{6}"
            maxLength={6}
            className="mt-1 block w-full rounded-lg border p-3"
            autoComplete="postal-code"
            value={location.postal_code}
            onChange={(event) =>
              setLocation({ ...location, postal_code: event.target.value })
            }
          />
        </label>
        <p className="text-sm text-slate-600">
          Set the map coordinates of the clinic's pickup entrance so the courier
          uses the right location.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium">
            Latitude
            <input
              required
              type="number"
              min="1.1"
              max="1.5"
              step="0.0000001"
              className="mt-1 block w-full rounded-lg border p-3"
              value={location.coordinates.lat}
              onChange={(event) =>
                setLocation({
                  ...location,
                  coordinates: {
                    ...location.coordinates,
                    lat: event.target.value,
                  },
                })
              }
            />
          </label>
          <label className="block text-sm font-medium">
            Longitude
            <input
              required
              type="number"
              min="103.5"
              max="104.1"
              step="0.0000001"
              className="mt-1 block w-full rounded-lg border p-3"
              value={location.coordinates.lng}
              onChange={(event) =>
                setLocation({
                  ...location,
                  coordinates: {
                    ...location.coordinates,
                    lng: event.target.value,
                  },
                })
              }
            />
          </label>
        </div>
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
