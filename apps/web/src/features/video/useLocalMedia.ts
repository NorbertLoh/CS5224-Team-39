import { useEffect, useRef, useState } from 'react'

export function mediaError(error: unknown) {
  const name = error instanceof Error ? error.name : ''
  if (name === 'NotAllowedError' || name === 'SecurityError')
    return 'Camera or microphone permission was denied. Allow access in your browser, then retry.'
  if (name === 'NotFoundError')
    return 'No camera or microphone was found. Connect your devices, then retry.'
  if (name === 'NotReadableError')
    return 'Your camera or microphone is busy. Close other apps using it, then retry.'
  return 'Could not start your camera and microphone. Check your devices and retry.'
}

export function useLocalMedia() {
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const [camera, setCamera] = useState(true)
  const [microphone, setMicrophone] = useState(true)
  const current = useRef<MediaStream | null>(null)
  const request = useRef(0)

  const stop = () => {
    request.current += 1
    current.current?.getTracks().forEach((track) => track.stop())
    current.current = null
    setStream(null)
    setPending(false)
  }

  useEffect(
    () => () => {
      request.current += 1
      current.current?.getTracks().forEach((track) => track.stop())
    },
    [],
  )

  const start = async () => {
    stop()
    const id = request.current
    setError('')
    if (!navigator.mediaDevices?.getUserMedia) {
      setError(
        'Camera access requires localhost or HTTPS and a supported browser.',
      )
      return
    }
    setPending(true)
    try {
      const next = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: true,
      })
      if (id !== request.current) {
        next.getTracks().forEach((track) => track.stop())
        return
      }
      current.current = next
      next.getTracks().forEach((track) =>
        track.addEventListener(
          'ended',
          () => {
            if (current.current !== next) return
            stop()
            setError(
              'A camera or microphone disconnected. Reconnect your devices, then retry.',
            )
          },
          { once: true },
        ),
      )
      setStream(next)
      setCamera(true)
      setMicrophone(true)
    } catch (failure) {
      if (id === request.current) setError(mediaError(failure))
    } finally {
      if (id === request.current) setPending(false)
    }
  }

  const toggleCamera = () => {
    current.current?.getVideoTracks().forEach((track) => {
      track.enabled = !camera
    })
    setCamera(!camera)
  }
  const toggleMicrophone = () => {
    current.current?.getAudioTracks().forEach((track) => {
      track.enabled = !microphone
    })
    setMicrophone(!microphone)
  }
  return {
    stream,
    pending,
    error,
    camera,
    microphone,
    start,
    stop,
    toggleCamera,
    toggleMicrophone,
  }
}

export type LocalMedia = ReturnType<typeof useLocalMedia>
