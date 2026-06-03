import { NextRequest } from "next/server"

const API_BASE = process.env.API_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { geometry, user_id } = body

    if (!geometry) {
      return Response.json(
        { error: "geometry is required" },
        { status: 400 }
      )
    }

    if (!user_id) {
      return Response.json(
        { error: "user_id is required — please log in" },
        { status: 401 }
      )
    }

    const res = await fetch(`${API_BASE}/api/datasets/upload`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id,
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
