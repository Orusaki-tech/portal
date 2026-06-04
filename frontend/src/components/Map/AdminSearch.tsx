"use client"

import { useEffect, useRef, useState } from "react"
import type { AdminLevel } from "@/types/polygon"

interface AdminFeature {
  id: string
  name: string
  level: AdminLevel
  pcode: string
  parentName?: string
}

interface AdminSearchProps {
  features: AdminFeature[]
  onSelect: (id: string, level: AdminLevel) => void
}

export default function AdminSearch({ features, onSelect }: AdminSearchProps) {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<AdminFeature[]>([])
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!query.trim()) {
      setResults([])
      return
    }
    const q = query.toLowerCase()
    const filtered = features
      .filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.pcode.toLowerCase().includes(q)
      )
      .slice(0, 50)
    setResults(filtered)
    setOpen(filtered.length > 0)
  }, [query, features])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <input
        type="text"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder="Search admin boundaries..."
        className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
      />
      {open && results.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded border border-gray-200 bg-white shadow-lg">
          {results.map((r) => (
            <li
              key={r.id}
              onClick={() => {
                onSelect(r.id, r.level)
                setQuery(r.name)
                setOpen(false)
              }}
              className="cursor-pointer border-b border-gray-100 px-3 py-2 text-sm hover:bg-blue-50"
            >
              <span className="font-medium">{r.name}</span>
              <span className="ml-2 text-xs text-gray-400">
                {r.level.toUpperCase()} — {r.pcode}
              </span>
              {r.parentName && (
                <span className="ml-2 text-xs text-gray-400">
                  {r.parentName}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
