import type { ReactNode } from 'react'

export function WorkspacePage({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <h1 className="text-3xl font-semibold">{title}</h1>
      {children}
    </main>
  )
}
