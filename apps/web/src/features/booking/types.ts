import type { Slot } from '../scheduling/api'

export type BookingSlot = Slot & { doctor_name: string }
