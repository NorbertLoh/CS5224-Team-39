import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError } from '../../lib/api'
import { consultationPrice } from '../../lib/money'
import { readSession } from '../../auth/session'
import { refundHistory, refundPayment, type Payment } from './api'
import { paymentTime } from './model'

const labels = {
  pending: 'Refund processing',
  succeeded: 'Refunded',
  failed: 'Refund failed',
  review: 'Support review required',
}

export function ConsultationRefund({ payment }: { payment: Payment }) {
  const [reason, setReason] = useState('')
  const [confirming, setConfirming] = useState(false)
  const cache = useQueryClient()
  const token = readSession()?.accessToken
  const history = useQuery({
    queryKey: ['billing', 'refunds', token, payment.payment_id],
    queryFn: ({ signal }) => refundHistory(payment.payment_id, signal),
    refetchInterval: 5000,
    retry: false,
  })
  const refund = useMutation({
    mutationFn: () => refundPayment(payment.payment_id, reason.trim()),
    retry: false,
    onSuccess: async () => {
      setConfirming(false)
      setReason('')
      await cache.invalidateQueries({ queryKey: ['billing'] })
      await cache.invalidateQueries({ queryKey: ['scheduling'] })
    },
    onError: async () => {
      // A timeout can follow a committed request; refresh before offering another action.
      await cache.invalidateQueries({ queryKey: ['billing'] })
    },
  })
  const latest = history.data?.[0]
  const available =
    history.isSuccess &&
    ((payment.status === 'succeeded' && !latest) || latest?.retry_allowed)
  const amount = consultationPrice(
    payment.amount.amount_minor,
    payment.amount.currency,
  )
  return (
    <section
      className="mt-4 space-y-3 rounded border p-3"
      aria-label="Consultation refund"
    >
      <h3 className="font-semibold">Consultation refund</h3>
      <p className="text-sm">
        Full refunds only. Cancel an upcoming appointment in Appointments first.
        Completed and no-show consultations can also be reviewed here.
      </p>
      {history.isPending && <p role="status">Loading refund history…</p>}
      {history.isError && (
        <p role="alert">
          Could not load refund history.{' '}
          <button className="underline" onClick={() => void history.refetch()}>
            Try again
          </button>
        </p>
      )}
      {history.data?.map((entry) => (
        <div key={entry.refund_id} className="space-y-1 border-t pt-2 text-sm">
          <p role="status" className="font-medium">
            {labels[entry.status]}
          </p>
          <p className="whitespace-pre-wrap break-words">{entry.reason}</p>
          <p>Requested {paymentTime(entry.created_at)}</p>
          <p className="break-words">Requested by: {entry.requested_by_name}</p>
          {entry.status === 'review' && (
            <p>
              Contact platform support with the payment reference. Do not issue
              another refund outside the app until this outcome is checked.
            </p>
          )}
          {entry.status === 'failed' && (
            <p>
              Stripe confirmed this refund failed. You may retry after resolving
              the cause.
            </p>
          )}
        </div>
      ))}
      {available && (
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (confirming) refund.mutate()
            else setConfirming(true)
          }}
        >
          <label className="block">
            Refund reason
            <textarea
              className="mt-1 block w-full rounded border p-2"
              required
              maxLength={1000}
              value={reason}
              disabled={refund.isPending || confirming}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          {confirming && (
            <p role="alert">
              Refund the full {amount} to the original payment method? This also
              reverses the clinic transfer and platform commission. This action
              cannot be undone.
            </p>
          )}
          <button
            className="rounded border px-3 py-2"
            disabled={!reason.trim() || refund.isPending}
            type="submit"
          >
            {refund.isPending
              ? 'Submitting…'
              : confirming
                ? `Confirm refund ${amount}`
                : latest?.retry_allowed
                  ? 'Retry full refund'
                  : 'Refund payment'}
          </button>
          {confirming && (
            <button
              className="ml-2 underline"
              type="button"
              disabled={refund.isPending}
              onClick={() => setConfirming(false)}
            >
              Go back
            </button>
          )}
        </form>
      )}
      {refund.isError && (
        <p role="alert">
          {refund.error instanceof ApiError && refund.error.status === 409
            ? 'This payment cannot be refunded. Cancel an active appointment first, or contact support with the payment reference.'
            : 'Could not confirm the refund request. Refresh the history before retrying; an accepted request will continue processing.'}
        </p>
      )}
      {refund.isSuccess && (
        <p role="status">
          Refund request recorded. Check the status above for completion.
        </p>
      )}
    </section>
  )
}
