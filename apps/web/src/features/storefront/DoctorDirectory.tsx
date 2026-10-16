import { useInfiniteQuery } from '@tanstack/react-query'
import { clinicDoctors } from '../clinics/api'
import { LoadingState } from '@/components/LoadingState'
import { ErrorState } from '@/components/ErrorState'
import { Button } from '@/components/ui/button'
import { DoctorList } from './DoctorList'

export function DoctorDirectory({ tenantId }: { tenantId: string }) {
  const query = useInfiniteQuery({
    queryKey: ['clinic-doctors', tenantId], initialPageParam: null as string | null,
    queryFn: ({ pageParam }) => clinicDoctors(tenantId, pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  })
  if (query.isPending) return <LoadingState message="Loading doctors..." />
  if (query.isError) return <ErrorState message="Could not load the doctors." onRetry={() => void query.refetch()} />
  return <><DoctorList doctors={query.data.pages.flatMap(page => page.items)} />{query.hasNextPage && <Button className="mt-5" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>Load more doctors</Button>}</>
}
