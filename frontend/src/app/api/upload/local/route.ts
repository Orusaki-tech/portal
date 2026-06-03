import { NextRequest } from "next/server"

const API_BASE = process.env.API_URL || "http://localhost:8000"

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const auth = request.headers.get("Authorization") || ""

    const res = await fetch(`${API_BASE}/upload/local`, {
      method: "POST",
      headers: auth ? { Authorization: auth } : {},
      body: formData,
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
