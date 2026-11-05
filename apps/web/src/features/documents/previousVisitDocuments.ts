import { listDocuments } from '@/features/documents/api'
import type { DocumentMetadata } from '@/features/documents/types'
import { previousVisits } from '@/features/records/api/visits'
import type { Appointment } from '@/features/scheduling/api'

export async function previousVisitDocuments(
  appointment: Appointment,
  cursor: string | null,
  signal: AbortSignal,
) {
  const visits = await previousVisits(appointment, cursor, signal, 10)
  const documents = await Promise.all(
    visits.items.map(async (visit) => {
      const items: DocumentMetadata[] = []
      const seen = new Set<string>()
      let next: string | null = null
      do {
        const page = await listDocuments(
          visit.appointment_id,
          next,
          signal,
          appointment.appointment_id,
        )
        if (page.items.some((item) => item.tenant_id !== visit.tenant_id))
          throw new Error('Invalid previous visit document context')
        items.push(...page.items)
        next = page.next_cursor ?? null
        if (next && seen.has(next))
          throw new Error('Could not finish document pagination')
        if (next) seen.add(next)
      } while (next)
      return items
    }),
  )
  return {
    items: documents.flat(),
    visits: visits.items,
    next_cursor: visits.next_cursor,
  }
}
