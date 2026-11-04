import { currentIdentity } from '@/auth/identity'
import { accessTokenPrincipal, readSession } from '@/auth/session'
import { useQuery } from '@tanstack/react-query'

export function useSchedulingIdentity(stableAcrossRefresh = false) {
  const token = readSession()?.accessToken
  const principal =
    stableAcrossRefresh && token ? accessTokenPrincipal(token) : null
  const cacheKey = principal ?? token
  const identity = useQuery({
    queryKey: [principal ? 'consultation-identity' : 'identity', cacheKey],
    queryFn: currentIdentity,
    enabled: Boolean(token),
    staleTime: 0,
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  })
  return { ...identity, token, cacheKey }
}
