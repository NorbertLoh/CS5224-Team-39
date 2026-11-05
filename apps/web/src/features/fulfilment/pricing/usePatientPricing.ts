import type { Order } from '@/features/fulfilment/api'
import { request } from '@/features/fulfilment/api/client'
import type { Prescription } from '@/features/records/types'
import { useQueries } from '@tanstack/react-query'

export function usePatientPricing(
  prescriptions: Prescription[],
  orders: Order[],
  token: string | undefined,
  subject: string,
) {
  const pending = prescriptions.filter(
    (prescription) =>
      prescription.patient_id === subject &&
      prescription.status === 'issued' &&
      prescription.items.length > 0 &&
      !orders.some(
        (order) =>
          order.patient_id === subject &&
          order.prescription_id === prescription.prescription_id &&
          order.tenant_id === prescription.tenant_id &&
          order.appointment_id === prescription.appointment_id,
      ),
  )
  const queries = useQueries({
    queries: pending.map((prescription) => ({
      queryKey: ['fulfilment', 'prescription-pricing', token, prescription.prescription_id],
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const result: { prescription_id: string; ready: boolean } = await (
          await request(
            `/prescriptions/${encodeURIComponent(prescription.prescription_id)}/pricing-status`,
            { signal },
          )
        ).json()
        if (result.prescription_id !== prescription.prescription_id)
          throw new Error('Pricing status unavailable.')
        return result.ready
      },
      retry: false,
      gcTime: 0,
      refetchInterval: 15000,
    })),
  })
  return new Map(
    pending.map((prescription, index) => [prescription.prescription_id, queries[index]]),
  )
}
