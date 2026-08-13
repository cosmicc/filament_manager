import { type ReactNode } from 'react'

export function EditorSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="editor-section">
      <header className="editor-section__header">
        <h3>{title}</h3>
        {description ? <p>{description}</p> : null}
      </header>
      <div className="editor-section__body">{children}</div>
    </section>
  )
}
