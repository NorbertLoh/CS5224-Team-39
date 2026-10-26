import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { readSession } from '../../auth/session'
import { ErrorState } from '../../components/ErrorState'
import { readPatientProfile, savePatientProfile } from './profileApi'
import type { PatientProfile } from './profileApi'

export function PatientProfilePage() {
  const token = readSession()?.accessToken
  const query = useQuery({
    queryKey: ['patient-profile', token],
    queryFn: ({ signal }) => readPatientProfile(signal),
    retry: false,
    gcTime: 0,
  })
  return (
    <main className="mx-auto max-w-2xl space-y-6 px-6 py-10">
      <div>
        <h1 className="text-3xl font-semibold">My profile</h1>
        <p className="mt-2 text-sm text-slate-600">
          Keep your name, contact number and delivery address up to date.
        </p>
      </div>
      {query.isPending ? (
        <p role="status">Loading your profile...</p>
      ) : query.isError ? (
        <ErrorState
          message="Could not load your profile."
          onRetry={() => void query.refetch()}
        />
      ) : (
        <ProfileEditor initial={query.data} token={token} />
      )}
    </main>
  )
}

function ProfileEditor({
  initial,
  token,
}: {
  initial: PatientProfile
  token?: string
}) {
  const client = useQueryClient()
  const [profile, setProfile] = useState(initial)
  const [saved, setSaved] = useState(initial)
  const dirty = JSON.stringify(profile) !== JSON.stringify(saved)
  const mutation = useMutation({
    mutationFn: () => savePatientProfile(profile),
    retry: false,
    onSuccess: (result) => {
      setProfile(result)
      setSaved(result)
      client.setQueryData(['patient-profile', token], result)
      void client.invalidateQueries({ queryKey: ['identity'] })
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
      <fieldset disabled={mutation.isPending} className="space-y-5">
        <label className="block text-sm font-medium">
          Name
          <input
            required
            maxLength={100}
            autoComplete="name"
            className="mt-1 block w-full rounded-lg border p-3"
            value={profile.name}
            onChange={(event) =>
              setProfile({ ...profile, name: event.target.value })
            }
          />
        </label>
        <label className="block text-sm font-medium">
          Contact number
          <input
            required
            type="tel"
            maxLength={24}
            autoComplete="tel"
            placeholder="e.g. +65 8123 4567"
            className="mt-1 block w-full rounded-lg border p-3"
            value={profile.phone_number}
            onChange={(event) =>
              setProfile({ ...profile, phone_number: event.target.value })
            }
          />
          <span className="mt-1 block text-xs font-normal text-slate-600">
            Use an 8-digit Singapore number or include +65. The courier uses
            your name and number for medicine delivery.
          </span>
        </label>
        <label className="block text-sm font-medium">
          Address
          <input
            required
            maxLength={300}
            autoComplete="street-address"
            className="mt-1 block w-full rounded-lg border p-3"
            value={profile.address_line}
            onChange={(event) =>
              setProfile({ ...profile, address_line: event.target.value })
            }
          />
        </label>
        <label className="block text-sm font-medium">
          Postal code
          <input
            required
            pattern="[0-9]{6}"
            maxLength={6}
            inputMode="numeric"
            autoComplete="postal-code"
            className="mt-1 block w-full rounded-lg border p-3"
            value={profile.postal_code}
            onChange={(event) =>
              setProfile({ ...profile, postal_code: event.target.value })
            }
          />
        </label>
        <p className="text-sm text-slate-600">
          Your saved address prefills medicine checkout. You can change the
          delivery address there before calculating the total.
        </p>
        <button
          disabled={!dirty}
          className="rounded-lg bg-slate-900 px-5 py-3 font-medium text-white disabled:opacity-50"
        >
          {mutation.isPending ? 'Saving profile...' : 'Save profile'}
        </button>
      </fieldset>
      {mutation.isSuccess && !dirty && (
        <p role="status" className="text-sm text-emerald-800">
          Profile saved.
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="text-sm text-red-700">
          Could not save your profile. Check your name, Singapore contact
          number, address and postcode, then try again.
        </p>
      )}
    </form>
  )
}
