import type { LocalMedia } from '@/features/video/hooks/useLocalMedia'
import type {
  CallState,
  RoomConnection,
} from '@/features/video/media/connection'
import { RoomCall } from '@/features/video/media/connection'
import { useEffect, useRef, useState } from 'react'

export function useRemoteCall(
  connection: RoomConnection | undefined,
  role: 'patient' | 'doctor',
  media: LocalMedia,
) {
  const [state, setState] = useState<CallState>('waiting')
  const [remote, setRemote] = useState<MediaStream | null>(null)
  const [error, setError] = useState('')
  const current = useRef<RoomCall | null>(null)
  const generation = useRef(0)

  useEffect(() => {
    current.current = null
    setRemote(null)
    setState('waiting')
    setError('')
    return () => {
      generation.current++
      current.current?.stop()
    }
  }, [connection, role])

  useEffect(() => {
    if (!media.stream && current.current) current.current.stop('disconnected')
  }, [media.stream])

  const leave = () => {
    generation.current++
    current.current?.stop('left')
    current.current = null
    media.stop()
    setRemote(null)
    setState('left')
    setError('')
  }

  const join = async () => {
    if (!connection) return
    leave()
    const id = generation.current
    setState('joining')
    const stream = await media.start()
    if (id !== generation.current || !stream) {
      if (id === generation.current) setState('disconnected')
      return
    }
    const call = new RoomCall(connection, role, {
      state: (next, message = '') => {
        if (id !== generation.current) return
        setState(next)
        setError(message)
        if (next === 'disconnected') media.stop()
      },
      remote: (value) => {
        if (id === generation.current) setRemote(value)
      },
    })
    current.current = call
    void call.start(stream)
  }

  return { state, remote, error, join, leave }
}
