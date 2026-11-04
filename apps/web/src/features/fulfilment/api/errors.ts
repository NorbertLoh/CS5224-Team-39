import { ApiError } from '@/lib/api'

export function fulfilmentError(error: unknown) {
  if (error instanceof ApiError && error.code === 'delivery_contact_required')
    return 'Confirm the recipient contact and delivery address with a new quote before payment.'
  if (error instanceof ApiError && error.code === 'medication_unpriced')
    return 'The clinic admin needs to price this prescription before you can order or pay. Try again once pricing is ready.'
  if (error instanceof ApiError && error.status === 422)
    return 'Check the recipient name, Singapore contact number, delivery address and six-digit postal code.'
  if (error instanceof ApiError && error.status === 409)
    return 'The order or quote changed, expired, or has a pending payment. Refresh its status before continuing.'
  return 'Could not verify the order or payment. Check your connection and session, then refresh. Keep the same payment attempt while its outcome is unknown.'
}

export function deliveryQuoteError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'clinic_location_missing')
      return 'The clinic needs to save its pickup location in Clinic Settings before delivery can be calculated.'
    if (error.code === 'clinic_location_unavailable')
      return 'The clinic pickup location could not be loaded. Try again later or contact the clinic.'
    if (error.code === 'delivery_unavailable')
      return 'Delivery pricing is unavailable. Contact the clinic to check delivery setup, or try again later.'
    if (error.code === 'unsupported_destination')
      return 'Delivery is not available for this postcode. Contact the clinic for supported delivery areas.'
    if (error.status === 401 || error.status === 403)
      return 'Your session could not be verified. Sign in again before calculating delivery.'
    if (error.status === 409 || error.status === 422)
      return fulfilmentError(error)
  }
  return 'Could not calculate delivery and the total. Check your connection and try again with the same address.'
}
