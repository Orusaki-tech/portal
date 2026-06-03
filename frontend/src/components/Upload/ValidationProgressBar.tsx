"use client"

interface ValidationProgressBarProps {
  total: number
  completed: number
  status: "pending" | "running" | "complete" | "error"
}

export default function ValidationProgressBar({
  total,
  completed,
  status,
}: ValidationProgressBarProps) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0

  if (status === "pending") return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-600">
          {status === "running" && "Validating polygons..."}
          {status === "complete" && "Validation complete"}
          {status === "error" && "Validation failed"}
        </span>
        <span className="font-medium text-gray-700">
          {completed} / {total} ({pct}%)
        </span>
      </div>

      <div className="h-2.5 overflow-hidden rounded-full bg-gray-200">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            status === "error"
              ? "bg-red-500"
              : status === "complete"
                ? "bg-green-500"
                : "bg-blue-500"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {status === "running" && (
        <div className="flex justify-center">
          <div className="mx-auto h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" />
        </div>
      )}
    </div>
  )
}
