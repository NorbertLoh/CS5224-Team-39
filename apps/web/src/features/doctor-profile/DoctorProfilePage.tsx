import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { ApiError } from '@/lib/api'
import { WorkspacePage } from '@/navigation/WorkspacePage'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { doctorProfile, removeDoctorPhoto, uploadDoctorPhoto } from './api'
import { DoctorPhoto } from './DoctorPhoto'

export function DoctorProfilePage() {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: ['doctor-profile'],
    queryFn: doctorProfile,
  })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const mutation = useMutation({
    mutationFn: async (file: File | null) => {
      if (file) return uploadDoctorPhoto(file)
      await removeDoctorPhoto()
      return { ...query.data!, photo_id: null }
    },
    onSuccess: (profile, file) => {
      client.setQueryData(['doctor-profile'], profile)
      void client.invalidateQueries({ queryKey: ['clinic-doctors'] })
      setMessage(file ? 'Profile photo saved.' : 'Profile photo removed.')
    },
    onError: (failure) => {
      setError(
        failure instanceof ApiError && failure.status === 413
          ? 'Choose a photo smaller than 2 MB.'
          : failure instanceof ApiError && failure.code === 'invalid_photo'
            ? 'Choose a valid PNG or JPEG, up to 4096 pixels per side (16 MP).'
            : 'Could not update your photo. Please try again.',
      )
    },
  })

  return (
    <WorkspacePage title="Doctor profile">
      {query.isPending ? (
        <LoadingState message="Loading your profile..." />
      ) : query.isError ? (
        <ErrorState
          message="Could not load your profile."
          onRetry={() => void query.refetch()}
        />
      ) : (
        <section
          aria-labelledby="profile-photo-heading"
          className="mt-6 max-w-xl rounded-xl border border-slate-200 bg-white p-6"
        >
          <h2 id="profile-photo-heading" className="text-lg font-semibold">
            Profile photo
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Your photo will be visible in the doctor list on your clinics’
            public storefronts.
          </p>
          <div className="mt-6 flex items-center gap-5">
            <DoctorPhoto
              doctorId={query.data.doctor_id}
              photoId={query.data.photo_id}
              className="size-24"
            />
            <div className="min-w-0 flex-1">
              <label
                htmlFor="doctor-photo"
                className="block text-sm font-medium"
              >
                {query.data.photo_id ? 'Replace photo' : 'Upload photo'}
              </label>
              <input
                id="doctor-photo"
                type="file"
                accept="image/png,image/jpeg"
                disabled={mutation.isPending}
                aria-describedby="doctor-photo-help"
                className="mt-2 block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-teal-50 file:px-3 file:py-2 file:font-medium file:text-teal-800"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  if (!file) return
                  setMessage('')
                  setError('')
                  if (!['image/png', 'image/jpeg'].includes(file.type)) {
                    setError('Choose a PNG or JPEG photo.')
                  } else if (file.size > 2 * 1024 * 1024) {
                    setError('Choose a photo smaller than 2 MB.')
                  } else {
                    mutation.mutate(file)
                  }
                }}
              />
            </div>
          </div>
          <p id="doctor-photo-help" className="mt-4 text-xs text-slate-500">
            PNG or JPEG, up to 2 MB and 4096 pixels per side (16 MP). Photos
            save automatically.
          </p>
          {query.data.photo_id && (
            <Button
              variant="outline"
              className="mt-4"
              disabled={mutation.isPending}
              onClick={() => {
                setMessage('')
                setError('')
                mutation.mutate(null)
              }}
            >
              Remove photo
            </Button>
          )}
          <p role="status" className="mt-3 text-sm text-teal-700">
            {mutation.isPending ? 'Saving photo...' : message}
          </p>
          {error && (
            <p role="alert" className="mt-3 text-sm text-red-700">
              {error}
            </p>
          )}
        </section>
      )}
    </WorkspacePage>
  )
}
