import { doctorPhotoUrl } from '@/features/doctor-profile/api'
import { Stethoscope } from 'lucide-react'
import { useState } from 'react'

export function DoctorPhoto({
  doctorId,
  photoId,
  className = 'size-12',
}: {
  doctorId: string
  photoId?: string | null
  className?: string
}) {
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null)
  return (
    <span
      className={`${className} flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-slate-100 text-teal-700`}
      aria-hidden="true"
    >
      {photoId && failedPhoto !== photoId ? (
        <img
          src={doctorPhotoUrl(doctorId, photoId)}
          alt=""
          className="size-full object-cover"
          onError={() => setFailedPhoto(photoId)}
        />
      ) : (
        <Stethoscope className="size-5" />
      )}
    </span>
  )
}
