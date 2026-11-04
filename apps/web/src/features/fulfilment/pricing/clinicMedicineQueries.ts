import { readSession } from '@/auth/session'
import { listOrderRows } from '@/features/fulfilment/api/orders'
import type { Prices, Prescription } from '@/features/fulfilment/api/pricing'
import { pricePath, request } from '@/features/fulfilment/api/pricing'
import type { CursorPage } from '@/lib/api-types'
import { pendingAttention } from '@/navigation/attention'
import { navigationItems } from '@/navigation/useNavigationAttention'
import { queryOptions, useQueries, useQuery } from '@tanstack/react-query'

const refresh = {
  staleTime: 15000,
  refetchInterval: 30000,
  retry: false,
} as const

export function prescriptionPrices(tenantId: string, token: string, id: string) {
  return queryOptions({
    queryKey: ['prescription-prices', token, tenantId, id],
    queryFn: async ({ signal }): Promise<Prices> =>
      (await request(pricePath(tenantId, id), { signal })).json(),
    ...refresh,
  })
}

export function useClinicPrescriptions(tenantId: string, token: string) {
  return useQuery({
    queryKey: ['clinic-prescription-pricing', token, tenantId],
    queryFn: ({ signal }) =>
      navigationItems<Prescription>(async (cursor) => {
        const params = cursor ? '?' + new URLSearchParams({ cursor }) : ''
        const response = await request(
          `/clinical-records/clinics/${encodeURIComponent(tenantId)}/prescription-pricing${params}`,
          { signal },
        )
        return response.json() as Promise<CursorPage<Prescription>>
      }),
    enabled: Boolean(tenantId && token),
    ...refresh,
  })
}

export function useClinicMedicineAttention(tenantId: string) {
  const token = readSession()?.accessToken ?? ''
  const prescriptions = useClinicPrescriptions(tenantId, token)
  const rows = prescriptions.data ?? []
  const prices = useQueries({
    queries: rows
      .filter((row) => row.items.length > 0)
      .map((row) => prescriptionPrices(tenantId, token, row.prescription_id)),
  })
  const priceById = new Map(prices.flatMap(({ data }) =>
    data ? [[data.prescription_id, data] as const] : [],
  ))
  const pricingCount = rows.filter((row) => {
    const saved = priceById.get(row.prescription_id)
    return saved && !saved.locked && row.items.some((line) =>
      !saved.items.some((item) => item.prescription_item_id === line.prescription_item_id),
    )
  }).length

  const delivery = useQuery({
    queryKey: ['fulfilment', 'clinic-delivery-attention', token, tenantId],
    queryFn: ({ signal }) => navigationItems((cursor) =>
      listOrderRows(tenantId, cursor, signal, 'newest', 100),
    ),
    enabled: Boolean(tenantId && token),
    ...refresh,
  })
  const deliveryCount = delivery.data?.filter((order) =>
    order.tenant_id === tenantId && order.status === 'paid' &&
    order.payment_status === 'succeeded' && order.medicine_status === 'not_ready',
  ).length

  return {
    pricing: pendingAttention(
      prescriptions.isSuccess && prices.every((price) => price.isSuccess)
        ? pricingCount : undefined,
      'Prescriptions that need medicine prices.',
    ),
    delivery: pendingAttention(
      delivery.isSuccess ? deliveryCount : undefined,
      'Paid orders that need medicine preparation.',
    ),
  }
}
