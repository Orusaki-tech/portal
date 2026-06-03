import { NextRequest } from "next/server"

const API_BASE = process.env.API_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { filename, content_type } = body

    if (!filename || !content_type) {
      return Response.json(
        { error: "filename and content_type are required" },
        { status: 400 }
      )
    }

    const res = await fetch(`${API_BASE}/upload/generate-url`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
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
