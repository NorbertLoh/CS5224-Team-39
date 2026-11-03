/** Underline-only tabs and section links; keyboard focus stays on the bottom edge. */
export function tabClassName(active: boolean) {
  return `inline-flex min-h-11 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-none border-b-2 bg-transparent px-3 py-2.5 text-sm font-medium whitespace-nowrap outline-none transition-colors hover:text-teal-900 focus-visible:shadow-[inset_0_-2px_0_0_#134e4a] ${active ? 'border-teal-700 text-teal-800' : 'border-transparent text-slate-500'}`
}
