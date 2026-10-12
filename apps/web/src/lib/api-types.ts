/** C01 wire types. Strings are opaque; these aliases do not validate responses. */
export type ResourceId = string
export type UtcTimestamp = string

export interface Money {
  amount_minor: number
  currency: string
}

export interface CursorPage<T> {
  items: T[]
  next_cursor: string | null
}

export interface ErrorDetail {
  field: string
  code: string
  message: string
}

export interface ErrorEnvelope {
  error: {
    code: string
    message: string
    request_id: string
    details: ErrorDetail[]
  }
}

export type ApiService =
  | 'identity' | 'tenant' | 'scheduling' | 'consultation' | 'clinical-records'
  | 'billing' | 'document' | 'fulfilment' | 'notification'

export type ApiPath = `/${ApiService}` | `/${ApiService}/${string}`
