export function ApplicationFailure() {
  return (
    <main className="fatal-error" role="alert" aria-live="assertive">
      <section className="card fatal-error__card">
        <p className="eyebrow">Application error</p>
        <h1>Filament Manager could not continue</h1>
        <p>The error was recorded when monitoring is enabled. Reload the application to try again.</p>
        <button className="button button--primary" type="button" onClick={() => window.location.reload()}>
          Reload application
        </button>
      </section>
    </main>
  )
}
