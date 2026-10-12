/** C01 wire types; feature pages define and validate their own response shapes. */
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
