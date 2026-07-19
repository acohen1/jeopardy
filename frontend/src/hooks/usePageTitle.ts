import { useEffect } from 'react'

/** Sets document.title while mounted; restores the previous title on unmount
 * (so navigating back to the library restores the app default). */
export function usePageTitle(title: string) {
  useEffect(() => {
    const prev = document.title
    document.title = title
    return () => {
      document.title = prev
    }
  }, [title])
}
