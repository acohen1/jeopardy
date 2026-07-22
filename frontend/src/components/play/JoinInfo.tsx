/** Shared join-info pieces for the lobby screen and the mid-game JoinPanel. */
import qrcode from 'qrcode-generator'
import { useMemo } from 'react'
import { clsx } from 'clsx'

/** QR of the join URL. White padding IS the quiet zone — scanners need it,
 * so the background stays white in both themes. */
export function JoinQr({ url, className }: { url: string; className?: string }) {
  const svg = useMemo(() => {
    const qr = qrcode(0, 'M')
    qr.addData(url)
    qr.make()
    return qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true })
  }, [url])

  return (
    <div className={clsx('shrink-0 rounded-xl bg-white p-3', className)}>
      <div
        aria-label={`QR code for ${url}`}
        role="img"
        className="[&_svg]:block [&_svg]:h-auto [&_svg]:w-full"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    </div>
  )
}
