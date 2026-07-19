import { createFileRoute } from '@tanstack/react-router'

import { boardsQuery } from '@/api/boards'
import { LibraryPage } from '@/components/library/LibraryPage'

export const Route = createFileRoute('/')({
  loader: ({ context }) => context.queryClient.ensureQueryData(boardsQuery()),
  component: LibraryPage,
})
