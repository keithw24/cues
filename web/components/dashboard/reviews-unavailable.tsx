/** Shown when the review feed failed or dropped, with a way to try again. */
export function ReviewsUnavailable({
  loading,
  onRetry,
}: {
  loading: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="list-notice" role="alert">
      <p>Couldn’t check for new requests.</p>
      <button
        type="button"
        className="ws-pill"
        disabled={loading}
        onClick={onRetry}
      >
        Try again
      </button>
    </div>
  );
}
