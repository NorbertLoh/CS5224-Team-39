import type { Slot } from '@/features/scheduling/api'

export type BookingSlot = Slot & { doctor_name: string }
