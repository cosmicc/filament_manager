import { ApiClientError, actionableApiError } from '../api/client'

export function FormSubmissionError({
  error,
  fieldLabel = (field) => field.replaceAll('_', ' '),
  conflictMessage,
}: {
  error: unknown
  fieldLabel?: (field: string) => string
  conflictMessage?: string
}) {
  if (!error) return null
  if (error instanceof ApiClientError && error.code === 'validation_error' && error.validationErrors.length) {
    return (
      <div className="form-error form-error--summary" role="alert">
        <strong>Correct the following values and save again:</strong>
        <ul>
          {error.validationErrors.map((issue, index) => (
            <li key={`${issue.field}-${issue.type}-${index}`}>
              <strong>{fieldLabel(issue.field)}:</strong> {issue.message}
            </li>
          ))}
        </ul>
        {error.correlationId ? <small>Diagnostic reference: {error.correlationId}</small> : null}
      </div>
    )
  }
  if (error instanceof ApiClientError && error.code === 'version_conflict' && conflictMessage) {
    return <p className="form-error" role="alert">{conflictMessage}</p>
  }
  return <p className="form-error" role="alert">{actionableApiError(error)}</p>
}
