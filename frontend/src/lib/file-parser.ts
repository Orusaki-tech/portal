import type { ParsedGeometry } from "@/types/polygon"

export interface FileParseResult {
  geometries: ParsedGeometry[]
  fileName: string
  geometryCount: number
  warnings: string[]
  errors: string[]
}

export async function parseFile(file: File): Promise<FileParseResult> {
  const ext = file.name.split(".").pop()?.toLowerCase()

  if (ext === "geojson" || ext === "json") {
    return parseGeoJSON(file)
  }

  if (ext === "csv") {
    return parseCSV(file)
  }

  if (ext === "zip") {
    return parseShapefile(file)
  }

  return {
    geometries: [],
    fileName: file.name,
    geometryCount: 0,
    warnings: [],
    errors: [`Unsupported file type: .${ext}. Use .geojson, .json, .csv, or .zip (Shapefile).`],
  }
}

async function parseGeoJSON(file: File): Promise<FileParseResult> {
  const text = await file.text()
  const data = JSON.parse(text)
  const geometries: ParsedGeometry[] = []
  const warnings: string[] = []
  const errors: string[] = []

  if (data.type === "FeatureCollection" && Array.isArray(data.features)) {
    let idx = 0
    for (const feature of data.features) {
      const result = extractPolygonFromFeature(feature, idx)
      if (result) {
        geometries.push(result)
      } else {
        warnings.push(`Feature at index ${idx} is not a Polygon/MultiPolygon — skipped`)
      }
      idx++
    }
  } else if (data.type === "Feature") {
    const result = extractPolygonFromFeature(data, 0)
    if (result) {
      geometries.push(result)
    } else {
      errors.push("GeoJSON Feature does not contain a Polygon geometry")
    }
  } else {
    errors.push("GeoJSON must be a FeatureCollection or Feature")
  }

  return { geometries, fileName: file.name, geometryCount: geometries.length, warnings, errors }
}

function extractPolygonFromFeature(
  feature: Record<string, unknown>,
  index: number
): ParsedGeometry | null {
  const geom = feature.geometry as Record<string, unknown> | undefined
  if (!geom) return null

  const geomType = geom.type as string

  if (geomType === "Polygon") {
    const coords = geom.coordinates as number[][][]
    return {
      id: `poly_${index}`,
      wkt: coordsToWKT(coords),
      coords,
      validation: null,
      status: "valid",
      properties: (feature.properties as Record<string, unknown>) || {},
    }
  }

  if (geomType === "MultiPolygon") {
    const multiCoords = geom.coordinates as number[][][][]
    return {
      id: `poly_${index}`,
      wkt: multiCoords.map((c) => coordsToWKT(c)).join(" "),
      coords: multiCoords[0],
      validation: null,
      status: "valid",
      properties: (feature.properties as Record<string, unknown>) || {},
    }
  }

  return null
}

async function parseCSV(file: File): Promise<FileParseResult> {
  const text = await file.text()
  const lines = text.split("\n").filter((l) => l.trim())
  const geometries: ParsedGeometry[] = []
  const warnings: string[] = []
  const errors: string[] = []

  if (lines.length < 2) {
    errors.push("CSV file has no data rows")
    return { geometries, fileName: file.name, geometryCount: 0, warnings, errors }
  }

  const header = lines[0].toLowerCase()
  const cols = header.split(",").map((c) => c.trim())

  const wktIdx = cols.findIndex(
    (c) => c === "wkt" || c === "geometry" || c === "geom" || c === "the_geom"
  )
  const latIdx = cols.findIndex((c) => c === "lat" || c === "latitude" || c === "y")
  const lngIdx = cols.findIndex((c) => c === "lng" || c === "lon" || c === "longitude" || c === "x")

  if (wktIdx >= 0) {
    for (let i = 1; i < lines.length; i++) {
      const parts = parseCSVLine(lines[i])
      const wkt = parts[wktIdx]?.trim()
      if (wkt && /^POLYGON/i.test(wkt)) {
        const coords = wktToCoords(wkt)
        if (coords) {
          geometries.push({
            id: `poly_${i - 1}`,
            wkt,
            coords,
            validation: null,
            status: "valid",
            properties: {},
          })
        } else {
          warnings.push(`Row ${i}: invalid WKT polygon — skipped`)
        }
      } else {
        warnings.push(`Row ${i}: no WKT polygon found — skipped`)
      }
    }
  } else if (latIdx >= 0 && lngIdx >= 0) {
    for (let i = 1; i < lines.length; i++) {
      const parts = parseCSVLine(lines[i])
      const lat = parseFloat(parts[latIdx])
      const lng = parseFloat(parts[lngIdx])
      if (!isNaN(lat) && !isNaN(lng)) {
        warnings.push(`Row ${i}: single point (${lng},${lat}) — cannot create polygon from point`)
      }
    }
    errors.push("CSV with lat/lon columns requires polygon boundaries, not points. Use WKT format instead.")
  } else {
    errors.push('CSV must have a "WKT" column containing POLYGON geometries')
  }

  return { geometries, fileName: file.name, geometryCount: geometries.length, warnings, errors }
}

async function parseShapefile(file: File): Promise<FileParseResult> {
  const arrayBuffer = await file.arrayBuffer()
  const geometries: ParsedGeometry[] = []
  const warnings: string[] = []
  const errors: string[] = []

  try {
    const shpjs = await import("shpjs")
    const data = await shpjs.default(arrayBuffer)

    const features = Array.isArray(data) ? data : [data]

    for (const feature of features) {
      if (feature.type !== "Polygon" && feature.type !== "MultiPolygon") {
        warnings.push(`Shapefile contains non-polygon geometry type: ${feature.type}`)
        continue
      }

      const coords = feature.type === "Polygon"
        ? (feature.coordinates as number[][][])
        : (feature.coordinates as number[][][][])[0]

      const wkt = coordsToWKT(coords)

      geometries.push({
        id: `shp_${geometries.length}`,
        wkt,
        coords,
        validation: null,
        status: "valid",
        properties: feature.properties || {},
      })
    }
  } catch (e) {
    errors.push(`Failed to parse Shapefile: ${e instanceof Error ? e.message : "Unknown error"}`)
  }

  return { geometries, fileName: file.name, geometryCount: geometries.length, warnings, errors }
}

function coordsToWKT(coords: number[][][]): string {
  const ring = coords[0]
    .map(([lng, lat]) => `${lng} ${lat}`)
    .join(", ")
  return `POLYGON((${ring}))`
}

function wktToCoords(wkt: string): number[][][] | null {
  const match = wkt.match(/POLYGON\s*\(\(([^)]+)\)\)/i)
  if (!match) return null
  const rings = match[1].split(/\),\s*\(/)
  return rings.map((ring) =>
    ring.split(",").map((pair) => {
      const [lng, lat] = pair.trim().split(/\s+/)
      return [parseFloat(lng), parseFloat(lat)]
    })
  )
}

function parseCSVLine(line: string): string[] {
  const result: string[] = []
  let current = ""
  let inQuotes = false

  for (const char of line) {
    if (char === '"') {
      inQuotes = !inQuotes
    } else if (char === "," && !inQuotes) {
      result.push(current)
      current = ""
    } else {
      current += char
    }
  }
  result.push(current)

  return result
}
