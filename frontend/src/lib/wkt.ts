export function wktToCoords(wkt: string): number[][][] | null {
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
