import { NextRequest } from "next/server"

const API_BASE = process.env.API_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { geometry } = body

    if (!geometry) {
      return Response.json(
        { error: "geometry is required" },
        { status: 400 }
      )
    }

    // Proxy to backend
    const res = await fetch(`${API_BASE}/api/datasets/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: "00000000-0000-0000-0000-000000000000",
        name: "Web Upload",
        geometries: [geometry],
      }),
    })

    if (!res.ok) {
      const text = await res.text()
      return Response.json({ error: text }, { status: res.status })
    }

    return Response.json(await res.json())
  } catch (err) {
    const message =
      err instanceof Error ? err.message : "Internal server error"
    return Response.json({ error: message }, { status: 500 })
  }
}
