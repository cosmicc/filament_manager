import { X } from 'lucide-react'
import { type ReactNode, useEffect, useId, useRef } from 'react'
import { createPortal } from 'react-dom'

// Child creation dialogs must not close or focus-trap their still-open parent.
const dialogs: HTMLElement[] = []
let restoredOverflow = ''
function updateDialogStack() {
  dialogs.forEach((dialog, index) => {
    dialog.inert = index !== dialogs.length - 1
    if (dialog.inert) dialog.setAttribute('aria-hidden', 'true')
    else dialog.removeAttribute('aria-hidden')
  })
}

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

export function Modal({ title, description, children, onClose, footer, size = 'standard' }: {
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
  footer?: ReactNode
  size?: 'standard' | 'wide'
}) {
  const titleId = useId()
  const descriptionId = useId()
  const dialogRef = useRef<HTMLElement>(null)
  const onCloseRef = useRef(onClose)
  // Capture before React applies a child's autoFocus during the commit phase.
  const returnFocusRef = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null)

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const previouslyFocused = returnFocusRef.current
    if (!dialogs.length) restoredOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'

    const dialog = dialogRef.current
    if (!dialog) return
    dialogs.push(dialog)
    updateDialogStack()
    const initialFocus = dialog?.querySelector<HTMLElement>('[autofocus]')
      ?? dialog?.querySelector<HTMLElement>('input, select, textarea, button')
    initialFocus?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (dialogs.at(-1) !== dialog) return
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab' || !dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(focusableSelector))
      if (!focusable.length) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      dialogs.splice(dialogs.indexOf(dialog), 1)
      updateDialogStack()
      if (!dialogs.length) document.body.style.overflow = restoredOverflow
      if (previouslyFocused?.isConnected) previouslyFocused.focus()
    }
  }, [])

  return createPortal(
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section
        className={`modal${size === 'wide' ? ' modal--wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        ref={dialogRef}
        tabIndex={-1}
      >
        <header className="modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p id={descriptionId}>{description}</p>}
          </div>
          <button className="icon-button" type="button" onClick={onClose} aria-label="Close dialog"><X size={20} /></button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__footer">{footer}</footer>}
      </section>
    </div>, document.body,
  )
}
