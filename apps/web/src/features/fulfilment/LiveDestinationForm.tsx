import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { createQuote, fulfilmentError } from './api'
import { stableKey } from './checkout'

export function LiveDestinationForm({
  orderId,
  subject,
  onRefresh,
  onEditingChange,
}: {
  orderId: string
  subject: string
  onRefresh: () => void
  onEditingChange: (value: boolean) => void
}) {
  const [address, setAddress] = useState('')
  const [postcode, setPostcode] = useState('')
  const quote = useMutation({
    mutationFn: async () => {
      const destination = {
        address_line: address.trim(),
        postal_code: postcode.trim(),
        country_code: 'SG' as const,
      }
      // Persist only the hash/key, never the delivery address.
      const hash = await crypto.subtle.digest(
        'SHA-256',
        new TextEncoder().encode(JSON.stringify(destination)),
      )
      const fingerprint = Array.from(new Uint8Array(hash), (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('')
      const scope = `telelink.quote.${subject}.${orderId}`
      const key = stableKey(sessionStorage, scope, fingerprint)
      const result = await createQuote(orderId, destination, key)
      if (result.order_id !== orderId) throw new Error('Quote unavailable.')
      sessionStorage.removeItem(scope)
      return result
    },
    retry: false,
    onSuccess: () => {
      setAddress('')
      setPostcode('')
      onEditingChange(false)
      onRefresh()
    },
  })
  return (
    <form
      className="space-y-3 rounded-xl border p-4"
      onSubmit={(event) => {
        event.preventDefault()
        quote.mutate()
      }}
    >
      <h3 className="font-semibold">Delivery address</h3>
      <p className="text-sm">
        Singapore delivery. The local prototype supports configured postcodes
        only. A new quote refreshes medication prices and the delivery fee.
      </p>
      <fieldset disabled={quote.isPending} className="space-y-3">
        <label className="block text-sm font-medium">
          Delivery address
          <input
            required
            maxLength={300}
            className="mt-1 block w-full rounded-lg border p-2"
            value={address}
            autoComplete="street-address"
            onChange={(event) => {
              setAddress(event.target.value)
              onEditingChange(true)
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
            value={postcode}
            autoComplete="postal-code"
            onChange={(event) => {
              setPostcode(event.target.value)
              onEditingChange(true)
            }}
          />
        </label>
        <button className="rounded-lg border px-4 py-2" type="submit">
          {quote.isPending ? 'Requesting quote...' : 'Request delivery quote'}
        </button>
      </fieldset>
      {quote.isError && (
        <p role="alert" className="text-sm text-red-700">
          {fulfilmentError(quote.error)}
        </p>
      )}
    </form>
  )
}
