import { createApiClient } from './api-client'

// A01/A02 can create an authenticated client with getAccessToken. No token storage here.
export const api = createApiClient({ baseUrl: import.meta.env.VITE_API_BASE_URL || '/api/v1' })
