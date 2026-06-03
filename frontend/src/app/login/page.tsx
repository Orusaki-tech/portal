"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { login, register } from "@/lib/api"

export default function LoginPage() {
  const router = useRouter()
  const [email, setEmail] = useState("")
  const [name, setName] = useState("")
  const [mode, setMode] = useState<"login" | "register">("login")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const key = localStorage.getItem("realitysync_api_key")
    if (key) router.push("/")
  }, [router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const result = mode === "login" ? await login(email) : await register(email, name || email.split("@")[0])
      localStorage.setItem("realitysync_api_key", result.api_key)
      localStorage.setItem("realitysync_user", JSON.stringify(result))
      router.push("/")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="mx-auto flex min-h-[80vh] max-w-sm items-center">
      <div className="w-full">
        <h1 className="mb-6 text-center text-2xl font-bold">RealitySync</h1>
        <p className="mb-6 text-center text-sm text-gray-500">
          {mode === "login" ? "Sign in with your email" : "Create an account"}
        </p>

        {error && (
          <div className="mb-4 rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              placeholder="you@example.com"
              required
            />
          </div>

          {mode === "register" && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
                placeholder="Your Name"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? "..." : mode === "login" ? "Sign In" : "Create Account"}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-gray-500">
          {mode === "login" ? (
            <>No account?{" "}<button onClick={() => setMode("register")} className="text-blue-600 hover:underline">Create one</button></>
          ) : (
            <>Already have one?{" "}<button onClick={() => setMode("login")} className="text-blue-600 hover:underline">Sign in</button></>
          )}
        </p>
      </div>
    </div>
  )
}
