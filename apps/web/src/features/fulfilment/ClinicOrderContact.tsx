import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '../../lib/api'
import { accessToken } from '../clinics/api'
import type { Appointment } from '../scheduling/api'
import { readDeliveryDetails } from './api'
import type { Order } from './api'

export function ClinicOrderContact({ order }: { order: Order }) {
  const details = useQuery({
    queryKey: [
      'clinic-order-contact',
      order.tenant_id,
      order.order_id,
      order.quote_id,
    ],
    queryFn: ({ signal }) => readDeliveryDetails(order.order_id, signal),
    retry: false,
    gcTime: 0,
  })
  const patient = useQuery({
    queryKey: ['clinic-order-patient', order.tenant_id, order.appointment_id],
    queryFn: async ({ signal }) => {
      const appointment: Appointment = await (
        await apiFetch(
          `/scheduling/appointments/${encodeURIComponent(order.appointment_id)}`,
          { accessToken: await accessToken(), signal },
        )
      ).json()
      if (
        appointment.tenant_id !== order.tenant_id ||
        appointment.patient_id !== order.patient_id
      )
        throw new Error('Patient unavailable')
      return appointment.patient_name
    },
    retry: false,
    gcTime: 0,
  })
  const saved = details.data
  return (
    <section
      aria-label="Patient and delivery details"
      className="space-y-3 rounded-xl border p-4"
    >
      <h3 className="font-semibold">Patient and delivery details</h3>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="font-medium">Patient name</dt>
          <dd>
            {patient.isPending
              ? 'Loading patient…'
              : patient.data || 'Patient name unavailable'}
          </dd>
        </div>
        <div>
          <dt className="font-medium">Delivery recipient</dt>
          <dd>{saved?.recipient?.name || 'Not confirmed'}</dd>
        </div>
        <div>
          <dt className="font-medium">Contact number</dt>
          <dd>{saved?.recipient?.phone_number || 'Not confirmed'}</dd>
        </div>
        <div>
          <dt className="font-medium">Delivery address</dt>
          <dd className="whitespace-pre-wrap break-words">
            {saved?.destination
              ? `${saved.destination.address_line}, Singapore ${saved.destination.postal_code}`
              : 'Not confirmed'}
          </dd>
        </div>
      </dl>
      {details.isPending && (
        <p role="status" className="text-sm">
          Loading delivery details…
        </p>
      )}
      {details.isError && (
        <p role="alert" className="text-sm text-red-700">
          Could not load saved delivery details.{' '}
          <button
            className="underline"
            onClick={() => {
              void details.refetch()
            }}
          >
            Try again
          </button>
        </p>
      )}
      {!details.isPending && !details.isError && !saved?.recipient && (
        <p className="text-sm text-slate-600">
          The patient has not confirmed contact details for this order. Older
          orders may not have a saved contact.
        </p>
      )}
    </section>
  )
}
