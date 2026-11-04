export type ListFilterValues = {
  q: string
  from: string
  to: string
  status: string
}
export const emptyFilters: ListFilterValues = {
  q: '',
  from: '',
  to: '',
  status: 'all',
}

export function appendFilters(
  params: URLSearchParams,
  filters: ListFilterValues,
) {
  if (filters.q.trim()) params.set('q', filters.q.trim())
  if (filters.from) params.set('from', `${filters.from}T00:00:00+08:00`)
  if (filters.to)
    params.set(
      'to',
      new Date(
        Date.parse(`${filters.to}T00:00:00+08:00`) + 86400000,
      ).toISOString(),
    )
  return params
}
