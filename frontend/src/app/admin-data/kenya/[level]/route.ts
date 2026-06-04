import { NextResponse } from "next/server"
import fs from "fs"
import path from "path"

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ level: string }> }
) {
  const { level } = await params
  const valid = ["admin0", "admin1", "admin2"]
  if (!valid.includes(level)) {
    return NextResponse.json({ error: "Invalid level" }, { status: 400 })
  }

  const cwd = process.cwd()
  const filePath = path.join(cwd, "public", "data", "kenya", `${level}.geojson`)

  try {
    const data = fs.readFileSync(filePath, "utf-8")
    return new NextResponse(data, {
      headers: { "Content-Type": "application/geo+json" },
    })
  } catch {
    return NextResponse.json({ error: "File not found", cwd, filePath }, { status: 404 })
  }
}

export const runtime = "nodejs"
