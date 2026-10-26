import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createQuote, deliveryQuoteError, readDeliveryDetails } from './api'
import type { DeliveryDetails } from './api'
import { stableKey } from './checkout'
import { readPatientProfile, savePatientProfile } from '../patient/profileApi'
import type { PatientProfile } from '../patient/profileApi'

type Props = {
  orderId: string
  quoteId: string | null
  subject: string
  editable?: boolean
  onRefresh: () => Promise<unknown>
  onEditingChange: (value: boolean) => void
}

export function LiveDestinationForm(props: Props) {
  const { orderId, quoteId, subject, editable = true } = props
  const profile = useQuery({
    queryKey: ['patient-profile', subject],
    queryFn: ({ signal }) => readPatientProfile(signal),
    enabled: editable,
    retry: false,
    gcTime: 0,
  })
  const details = useQuery({
    queryKey: ['order-delivery-details', subject, orderId, quoteId],
    queryFn: ({ signal }) => readDeliveryDetails(orderId, signal),
    retry: false,
    gcTime: 0,
  })
  if (details.isPending || (editable && profile.isPending))
    return <p role="status">Loading delivery details...</p>
  if (details.isError)
    return (
      <p role="alert">
        Could not load this order’s delivery details. Refresh before continuing.
      </p>
    )
  if (!editable)
    return (
      <section
        className="space-y-1 rounded-xl border p-4 text-sm"
        aria-label="Confirmed delivery details"
      >
        <h3 className="font-semibold">Confirmed delivery details</h3>
        <p>
          {details.data.recipient?.name} ·{' '}
          {details.data.recipient?.phone_number}
        </p>
        <p>
          {details.data.destination?.address_line}, Singapore{' '}
          {details.data.destination?.postal_code}
        </p>
      </section>
    )
  const initial =
    profile.data?.subject_id === subject ? profile.data : undefined
  return (
    <DestinationForm
      key={orderId}
      {...props}
      initial={initial}
      saved={details.data}
      profileUnavailable={profile.isError}
    />
  )
}

function DestinationForm({
  orderId,
  subject,
  onRefresh,
  onEditingChange,
  initial,
  saved,
  profileUnavailable,
}: Props & {
  initial?: PatientProfile
  saved: DeliveryDetails
  profileUnavailable: boolean
}) {
  const client = useQueryClient()
  const [name, setName] = useState(saved.recipient?.name ?? initial?.name ?? '')
  const [phone, setPhone] = useState(
    saved.recipient?.phone_number ?? initial?.phone_number ?? '',
  )
  const [address, setAddress] = useState(
    saved.destination?.address_line ?? initial?.address_line ?? '',
  )
  const [postcode, setPostcode] = useState(
    saved.destination?.postal_code ?? initial?.postal_code ?? '',
  )
  const [saveToProfile, setSaveToProfile] = useState(false)
  const [profileMessage, setProfileMessage] = useState('')
  const [profileError, setProfileError] = useState('')
  const quote = useMutation({
    mutationFn: async () => {
      setProfileMessage('')
      setProfileError('')
      const digits = phone.replace(/[ ()-]/g, '')
      const recipient = {
        name: name.trim(),
        phone_number: digits.length === 8 ? `+65${digits}` : digits,
      }
      const destination = {
        address_line: address.trim(),
        postal_code: postcode.trim(),
        country_code: 'SG' as const,
      }
      if (saveToProfile) {
        try {
          const updated = await savePatientProfile({
            subject_id: subject,
            name: recipient.name,
            phone_number: recipient.phone_number,
            ...destination,
          })
          client.setQueryData(['patient-profile', subject], updated)
          setProfileMessage('These details have been saved to your profile.')
        } catch (error) {
          setProfileError(
            'Could not save these details to your profile. Try again, or uncheck Save to my profile to use them only for this order.',
          )
          throw error
        }
      }
      const hash = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(JSON.stringify({ destination, recipient })),
      )
      const fingerprint = Array.from(new Uint8Array(hash), (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('')
      const scope = `telelink.quote.${subject}.${orderId}`
      // Browser storage contains only the fingerprint/key, never contact details.
      const key = stableKey(sessionStorage, scope, fingerprint)
      const result = await createQuote(orderId, destination, key, recipient)
      if (result.order_id !== orderId) throw new Error('Quote unavailable.')
      sessionStorage.removeItem(scope)
      client.setQueryData(
        ['order-delivery-details', subject, orderId, result.quote_id],
        { quote_id: result.quote_id, destination, recipient },
      )
      return result
    },
    retry: false,
    onSuccess: async () => {
      await onRefresh()
      onEditingChange(false)
    },
  })
  function changed() {
    onEditingChange(true)
    setProfileMessage('')
    quote.reset()
  }
  return (
    <form
      className="space-y-3 rounded-xl border p-4"
      aria-label="Delivery contact and address"
      onSubmit={(event) => {
        event.preventDefault()
        quote.mutate()
      }}
    >
      <h3 className="font-semibold">Delivery contact and address</h3>
      <p className="text-sm">
        Confirm who will receive your medicines and where to deliver them before
        payment. Delivery is available for supported Singapore postcodes only.
      </p>
      {profileUnavailable && (
        <p role="status" className="text-sm">
          Your profile could not be loaded. Enter the delivery details below.
        </p>
      )}
      <fieldset disabled={quote.isPending} className="space-y-3">
        <label className="block text-sm font-medium">
          Recipient name
          <input
            required
            pattern=".*\S.*"
            maxLength={100}
            className="mt-1 block w-full rounded-lg border p-2"
            autoComplete="name"
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              changed()
            }}
          />
        </label>
        <label className="block text-sm font-medium">
          Contact number
          <input
            required
            type="tel"
            pattern="(?:\+65[ \-]?)?[689](?:[ \-]?[0-9]){7}"
            title="Enter an 8-digit Singapore number, with optional +65."
            maxLength={24}
            className="mt-1 block w-full rounded-lg border p-2"
            autoComplete="tel"
            placeholder="e.g. +65 8123 4567"
            value={phone}
            onChange={(event) => {
              setPhone(event.target.value)
              changed()
            }}
          />
        </label>
        <label className="block text-sm font-medium">
          Delivery address
          <input
            required
            pattern=".*\S.*"
            maxLength={300}
            className="mt-1 block w-full rounded-lg border p-2"
            autoComplete="street-address"
            value={address}
            onChange={(event) => {
              setAddress(event.target.value)
              changed()
            }}
          />
        </label>
        <label className="block text-sm font-medium">
          Postal code
          <input
            required
            pattern="[0-9]{6}"
            maxLength={6}
            inputMode="numeric"
            className="mt-1 block w-full rounded-lg border p-2"
            autoComplete="postal-code"
            value={postcode}
            onChange={(event) => {
              setPostcode(event.target.value)
              changed()
            }}
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={saveToProfile}
            onChange={(event) => {
              setSaveToProfile(event.target.checked)
              onEditingChange(true)
              quote.reset()
              setProfileError('')
            }}
          />{' '}
          Save to my profile
        </label>
        <p className="text-sm text-slate-600">
          Otherwise, these details are used only for this order. Later profile
          changes will not change the confirmed order.
        </p>
        <button className="rounded-lg border px-4 py-2" type="submit">
          {quote.isPending
            ? 'Confirming details and calculating total...'
            : 'Confirm details & calculate total'}
        </button>
      </fieldset>
      {profileMessage && (
        <p role="status" className="text-sm">
          {profileMessage}
        </p>
      )}
      {quote.isSuccess && (
        <p role="status" className="text-sm">
          Delivery details confirmed for this order. Review the total before
          continuing to payment.
        </p>
      )}
      {quote.isError && (
        <p role="alert" className="text-sm text-red-700">
          {profileError || deliveryQuoteError(quote.error)}
        </p>
      )}
    </form>
  )
}
