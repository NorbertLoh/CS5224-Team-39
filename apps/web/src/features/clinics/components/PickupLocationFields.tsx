export type PickupLocation = {
  address_line: string
  postal_code: string
  country_code: 'SG'
  coordinates: { lat: string; lng: string }
  pickup_contact?: { name: string; phone: string } | null
}

export function emptyPickupLocation(): PickupLocation {
  return {
    address_line: '',
    postal_code: '',
    country_code: 'SG',
    coordinates: { lat: '', lng: '' },
    pickup_contact: { name: '', phone: '' },
  }
}

export function PickupLocationFields({
  location,
  setLocation,
}: {
  location: PickupLocation
  setLocation: (location: PickupLocation) => void
}) {
  return (
    <>
      <h3 className="font-semibold">Pickup contact</h3>
      <p className="text-sm text-slate-600">
        The courier uses these details to contact the clinic for medicine
        pickup.
      </p>
      <label className="block text-sm font-medium">
        Pickup contact name
        <input
          required
          maxLength={100}
          className="mt-1 block w-full rounded-lg border p-3"
          autoComplete="name"
          value={location.pickup_contact?.name ?? ''}
          onChange={(event) =>
            setLocation({
              ...location,
              pickup_contact: {
                name: event.target.value,
                phone: location.pickup_contact?.phone ?? '',
              },
            })
          }
        />
      </label>
      <label className="block text-sm font-medium">
        Pickup phone number
        <input
          required
          type="tel"
          maxLength={24}
          className="mt-1 block w-full rounded-lg border p-3"
          autoComplete="tel"
          placeholder="e.g. +65 8123 4567"
          value={location.pickup_contact?.phone ?? ''}
          onChange={(event) =>
            setLocation({
              ...location,
              pickup_contact: {
                name: location.pickup_contact?.name ?? '',
                phone: event.target.value,
              },
            })
          }
        />
      </label>
      <p className="text-sm text-slate-600">
        Use an 8-digit Singapore number or include +65.
      </p>
      <h3 className="font-semibold">Pickup location</h3>
      <label className="block text-sm font-medium">
        Clinic pickup address
        <input
          required
          maxLength={300}
          className="mt-1 block w-full rounded-lg border p-3"
          autoComplete="street-address"
          value={location.address_line}
          onChange={(event) =>
            setLocation({ ...location, address_line: event.target.value })
          }
        />
      </label>
      <label className="block text-sm font-medium">
        Postal code
        <input
          required
          pattern="[0-9]{6}"
          maxLength={6}
          className="mt-1 block w-full rounded-lg border p-3"
          autoComplete="postal-code"
          value={location.postal_code}
          onChange={(event) =>
            setLocation({ ...location, postal_code: event.target.value })
          }
        />
      </label>
      <p className="text-sm text-slate-600">
        Set the map coordinates of the clinic's pickup entrance so the courier
        uses the right location.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block text-sm font-medium">
          Latitude
          <input
            required
            type="number"
            min="1.1"
            max="1.5"
            step="0.0000001"
            className="mt-1 block w-full rounded-lg border p-3"
            value={location.coordinates.lat}
            onChange={(event) =>
              setLocation({
                ...location,
                coordinates: {
                  ...location.coordinates,
                  lat: event.target.value,
                },
              })
            }
          />
        </label>
        <label className="block text-sm font-medium">
          Longitude
          <input
            required
            type="number"
            min="103.5"
            max="104.1"
            step="0.0000001"
            className="mt-1 block w-full rounded-lg border p-3"
            value={location.coordinates.lng}
            onChange={(event) =>
              setLocation({
                ...location,
                coordinates: {
                  ...location.coordinates,
                  lng: event.target.value,
                },
              })
            }
          />
        </label>
      </div>
    </>
  )
}
