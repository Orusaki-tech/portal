"use client"

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <div className="flex min-h-[50vh] items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h2 className="mb-2 text-xl font-semibold text-gray-800">Something went wrong</h2>
        <p className="mb-6 text-sm text-gray-500">
          {error.message || "An unexpected error occurred. Please try again."}
        </p>
        <button
          onClick={reset}
          className="rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700"
        >
          Try again
        </button>
      </div>
    </div>
  )
}