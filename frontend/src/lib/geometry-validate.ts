import type {
  GeometryValidationResult,
  ParsedGeometry,
} from "@/types/polygon"
import { validateGeometries as apiValidateGeometries } from "@/lib/api"

export async function validateGeometries(
  geometries: ParsedGeometry[]
): Promise<ParsedGeometry[]> {
  const results = await Promise.allSettled(
    geometries.map(async (g) => {
      const clientResult = clientSideValidation(g.coords)
      const serverResult = await serverSideValidation(g.wkt, g.id)

      return {
        ...g,
        validation: mergeValidation(clientResult, serverResult),
        status: computeStatus(mergeValidation(clientResult, serverResult)),
      }
    })
  )

  return results.map((r, i) => {
    if (r.status === "fulfilled") return r.value
    return {
      ...geometries[i],
      validation: {
        index: i,
        vertexCount: 0,
        areaSqM: 0,
        isValid: false,
        isSimple: false,
        hasSelfIntersections: true,
        hasWrongRingOrientation: false,
        isDegenerate: true,
        bbox: null,
        warnings: [],
        errors: ["Validation failed"],
      },
      status: "error" as const,
    }
  })
}

export function clientSideValidation(
  coords: number[][][]
): Partial<GeometryValidationResult> {
  const ring = coords[0]
  const warnings: string[] = []
  const errors: string[] = []
  const vertexCount = ring.length

  let areaSqM = 0
  if (vertexCount >= 3) {
    areaSqM = calculateArea(ring)
  }

  const selfIntersections = detectSelfIntersections(ring)
  const hasSelfIntersections = selfIntersections.length > 0

  const isDegenerate = areaSqM < 0.01 || vertexCount < 3

  const bbox = computeBBox(ring)

  if (hasSelfIntersections) {
    errors.push(`Self-intersection detected at ${selfIntersections.length} point(s)`)
  }
  if (isDegenerate) {
    errors.push("Geometry is degenerate (zero area or too few vertices)")
  }
  if (vertexCount > 500) {
    warnings.push(`Large polygon: ${vertexCount} vertices — may impact performance`)
  }
  if (vertexCount < 3) {
    errors.push(`Too few vertices: ${vertexCount} (minimum 3 required)`)
  }

  return {
    vertexCount,
    areaSqM,
    isSimple: !hasSelfIntersections,
    hasSelfIntersections,
    isDegenerate,
    bbox,
    warnings,
    errors,
  }
}

async function serverSideValidation(
  wkt: string,
  id: string
): Promise<Partial<GeometryValidationResult> | null> {
  try {
    const results = await apiValidateGeometries([{ wkt, id }])
    return results[0] || null
  } catch {
    return null
  }
}

function mergeValidation(
  client: Partial<GeometryValidationResult>,
  server: Partial<GeometryValidationResult> | null
): GeometryValidationResult {
  const merged: GeometryValidationResult = {
    index: client.index ?? server?.index ?? 0,
    vertexCount: client.vertexCount ?? server?.vertexCount ?? 0,
    areaSqM: client.areaSqM ?? server?.areaSqM ?? 0,
    isValid: client.isValid ?? server?.isValid ?? true,
    isSimple: client.isSimple ?? server?.isSimple ?? true,
    hasSelfIntersections:
      client.hasSelfIntersections ?? server?.hasSelfIntersections ?? false,
    hasWrongRingOrientation:
      client.hasWrongRingOrientation ??
      server?.hasWrongRingOrientation ??
      false,
    isDegenerate: client.isDegenerate ?? server?.isDegenerate ?? false,
    bbox: client.bbox ?? server?.bbox ?? null,
    warnings: [...(client.warnings ?? []), ...(server?.warnings ?? [])],
    errors: [...(client.errors ?? []), ...(server?.errors ?? [])],
  }

  merged.isValid = merged.errors.length === 0
  merged.isSimple = !merged.hasSelfIntersections

  return merged
}

function computeStatus(
  validation: GeometryValidationResult
): "valid" | "warning" | "error" {
  if (validation.errors.length > 0) return "error"
  if (validation.warnings.length > 0) return "warning"
  return "valid"
}

function calculateArea(ring: number[][]): number {
  if (ring.length < 3) return 0

  let area = 0
  const n = ring.length
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n
    const [x1, y1] = ring[i]
    const [x2, y2] = ring[j]
    area += x1 * y2
    area -= x2 * y1
  }
  area = Math.abs(area) / 2

  const metersPerDegree = 111320
  const avgY =
    ring.reduce((s, [, y]) => s + y, 0) / ring.length
  const cosLat = Math.cos((avgY * Math.PI) / 180)
  return area * metersPerDegree * metersPerDegree * cosLat
}

function detectSelfIntersections(
  ring: number[][]
): Array<[number, number]> {
  const intersections: Array<[number, number]> = []

  for (let i = 0; i < ring.length; i++) {
    const j = (i + 1) % ring.length
    const p1 = ring[i]
    const p2 = ring[j]

    for (let k = i + 2; k < ring.length; k++) {
      const l = (k + 1) % ring.length
      if (l === i || l === j) continue

      const q1 = ring[k]
      const q2 = ring[l]

      const intersection = segmentsIntersect(p1, p2, q1, q2)
      if (intersection) {
        if (
          !intersections.some(
            ([x, y]) =>
              Math.abs(x - intersection[0]) < 0.0001 &&
              Math.abs(y - intersection[1]) < 0.0001
          )
        ) {
          intersections.push(intersection)
        }
      }
    }
  }

  return intersections
}

function segmentsIntersect(
  p1: number[],
  p2: number[],
  q1: number[],
  q2: number[]
): [number, number] | null {
  const d1x = p2[0] - p1[0]
  const d1y = p2[1] - p1[1]
  const d2x = q2[0] - q1[0]
  const d2y = q2[1] - q1[1]

  const cross = d1x * d2y - d1y * d2x
  if (Math.abs(cross) < 1e-10) return null

  const dx = q1[0] - p1[0]
  const dy = q1[1] - p1[1]

  const t = (dx * d2y - dy * d2x) / cross
  const u = (dx * d1y - dy * d1x) / cross

  if (t >= 0 && t <= 1 && u >= 0 && u <= 1) {
    return [p1[0] + t * d1x, p1[1] + t * d1y]
  }

  return null
}

function computeBBox(
  ring: number[][]
): [number, number, number, number] | null {
  if (ring.length === 0) return null

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  for (const [x, y] of ring) {
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }

  return [minX, minY, maxX, maxY]
}
