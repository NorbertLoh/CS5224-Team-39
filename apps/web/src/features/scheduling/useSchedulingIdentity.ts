import { useQuery } from '@tanstack/react-query'
import { readSession } from '../../auth/session'
import { currentIdentity } from '../clinics/api'

export function useSchedulingIdentity() {
  const token = readSession()?.accessToken
  const identity = useQuery({
    queryKey: ['identity', token],
    queryFn: currentIdentity,
    enabled: Boolean(token),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  })
  return { ...identity, token }
}
