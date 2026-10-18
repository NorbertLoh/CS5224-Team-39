import { useMutation, useQuery } from '@tanstack/react-query'
import { useSchedulingIdentity } from '../scheduling/useSchedulingIdentity'
import { appointmentDetail } from '../scheduling/api'
import { paymentDetail } from '../payments/api'
import { CheckoutStatus } from './CheckoutStatus'
import {
  beginCheckout,
  billingError,
  canCheckout,
  liveCheckoutState,
} from './live'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'

export function LiveCheckoutPage() {
  const identity = useSchedulingIdentity()
  if (identity.isError)
    return (
      <ErrorState
        message={billingError}
        onRetry={() => void identity.refetch()}
      />
    )
  if (!identity.data)
    return <LoadingState message="Checking payment access..." />
  return (
    <PaymentReturn
      key={identity.data.subject_id}
      subject={identity.data.subject_id}
      token={identity.token}
    />
  )
}

function PaymentReturn({
  subject,
  token,
}: {
  subject: string
  token?: string
}) {
  const supplied = new URLSearchParams(window.location.search).get(
    'appointment_id',
  )
  const id =
    supplied ?? sessionStorage.getItem(`telelink.checkout-return.${subject}`)
  const valid = Boolean(
    id &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        id,
      ),
  )
  const query = useQuery({
    queryKey: ['billing', 'return', token, subject, id],
    enabled: valid,
    queryFn: async ({ signal }) => {
      const appointment = await appointmentDetail(id!, signal)
      if (appointment.patient_id !== subject)
        throw new Error('Booking unavailable.')
      const payment = appointment.payment_id
        ? await paymentDetail(appointment.payment_id, signal)
        : null
      return {
        appointment,
        payment,
        state: liveCheckoutState(appointment, payment),
      }
    },
    retry: false,
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
  const checkout = useMutation({
    mutationFn: async () => {
      const refreshed = await query.refetch()
      if (refreshed.isError || !refreshed.data)
        throw new Error('Booking unavailable.')
      return beginCheckout(
        subject,
        refreshed.data.appointment,
        refreshed.data.payment,
      )
    },
    onSuccess: (url) => window.location.assign(url),
    retry: false,
  })
  const data = query.isError ? undefined : query.data
  const state = !valid
    ? 'missing'
    : query.isError
      ? 'error'
      : data && !data.payment && canCheckout(data.appointment, null)
        ? 'ready'
        : (data?.state ?? 'return')
  return (
    <main className="mx-auto max-w-2xl space-y-4 px-4 py-8">
      <CheckoutStatus
        state={state}
        busy={query.isFetching || checkout.isPending}
        onCheck={() => void query.refetch()}
        onRetry={() => checkout.mutate()}
        summary={
          data
            ? {
                appointmentId: data.appointment.appointment_id,
                paymentId: data.payment?.payment_id ?? null,
                startsAt: data.appointment.starts_at,
                amount:
                  data.payment?.amount ?? data.appointment.consultation_price,
              }
            : undefined
        }
      />
      {data?.appointment.hold_expires_at && (
        <p className="text-sm text-slate-600">
          Original booking deadline:{' '}
          {new Date(data.appointment.hold_expires_at).toLocaleString('en-SG', {
            timeZone: 'Asia/Singapore',
          })}{' '}
          SGT
        </p>
      )}
      {data &&
        canCheckout(data.appointment, data.payment) &&
        state !== 'failed' && (
          <button
            className="rounded border px-4 py-3"
            disabled={checkout.isPending || query.isFetching}
            onClick={() => checkout.mutate()}
          >
            Continue to secure checkout
          </button>
        )}
      {checkout.isError && (
        <ErrorState
          message={billingError}
          onRetry={() => void query.refetch()}
        />
      )}
    </main>
  )
}
