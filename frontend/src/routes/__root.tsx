import { useQueryClient, type QueryClient } from '@tanstack/react-query'
import { Outlet, createRootRouteWithContext, useNavigate } from '@tanstack/react-router'
import { Keyboard } from 'lucide-react'
import { useEffect, useState } from 'react'

import { WhatsNewDialog } from '@/components/desktop/WhatsNewDialog'
import { HotkeysDialog } from '@/components/ui/HotkeysDialog'
import { Toaster, toast } from '@/components/ui/Toaster'
import { useHotkeys } from '@/hooks/useHotkeys'
import { desktop } from '@/lib/desktop'

export interface RouterContext {
  queryClient: QueryClient
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
})

function RootLayout() {
  const [hotkeysOpen, setHotkeysOpen] = useState(false)
  useHotkeys({ '?': () => setHotkeysOpen(true) })

  // Desktop only: the Electron shell imported a double-clicked .rhubarb (or legacy .jeopardy) file.
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  useEffect(() => {
    if (!desktop) return
    return desktop.onImported(() => {
      toast('Board imported', { kind: 'success' })
      queryClient.invalidateQueries({ queryKey: ['boards'] })
      navigate({ to: '/' })
    })
  }, [queryClient, navigate])

  return (
    <div className="flex min-h-dvh flex-col">
      <Outlet />
      <Toaster />

      {/* Discreet, ever-present shortcuts affordance (bottom-right). */}
      <button
        type="button"
        onClick={() => setHotkeysOpen(true)}
        title="Keyboard shortcuts  [?]"
        aria-label="Keyboard shortcuts"
        className="text-ink-muted border-line/60 bg-bg/80 hover:text-ink hover:border-line fixed right-3 bottom-3 z-30 cursor-pointer rounded-full border p-2 opacity-50 backdrop-blur transition-all duration-150 hover:opacity-100"
      >
        <Keyboard size={15} />
      </button>

      <HotkeysDialog open={hotkeysOpen} onClose={() => setHotkeysOpen(false)} />

      {/* Desktop only: post-update release notes (renders null in browser). */}
      <WhatsNewDialog />
    </div>
  )
}
