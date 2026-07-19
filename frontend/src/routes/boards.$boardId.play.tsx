import { createFileRoute } from '@tanstack/react-router'

import { boardQuery } from '@/api/boards'
import { PlayMode } from '@/components/play/PlayMode'

export const Route = createFileRoute('/boards/$boardId/play')({
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(boardQuery(params.boardId)),
  component: PlayPage,
})

/** Play mode — gameplay board, scoreboard, and clue overlay. */
function PlayPage() {
  const { boardId } = Route.useParams()
  return <PlayMode boardId={boardId} />
}
