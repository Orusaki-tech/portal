"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import * as turf from "@turf/turf"
import type { ImagerySource, AdminLevel } from "@/types/polygon"

interface ImageryModalProps {
  open: boolean
  feature: GeoJSON.Feature
  name: string
  level: AdminLevel
  selectedSource: ImagerySource
  userSources: ImagerySource[]
  onClose: () => void
}

const TITILER_URL = "https://realitysync-titiler-111963419931.us-east1.run.app"
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"

function computeBbox(feature?: GeoJSON.Feature): [number, number, number, number] {
  if (!feature?.geometry) return [37, -4, 38, 4]
  const coords = feature.geometry.type === "Polygon"
    ? feature.geometry.coordinates[0]
    : feature.geometry.type === "MultiPolygon"
      ? feature.geometry.coordinates.flatMap((p) => p[0])
      : []
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const [x, y] of coords) {
    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x > maxX) maxX = x
    if (y > maxY) maxY = y
  }
  return [minX, minY, maxX, maxY]
}

export default function ImageryModal({
  open,
  feature,
  name,
  level,
  selectedSource,
  userSources,
  onClose,
}: ImageryModalProps) {
  const [buffer, setBuffer] = useState(0)
  const [activeSourceId, setActiveSourceId] = useState(selectedSource.id)
  const [downloading, setDownloading] = useState<string | null>(null)

  const mapContainer = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const mapReady = useRef(false)

  const allSources = [selectedSource, ...userSources.filter((s) => s.id !== selectedSource.id)]
  const activeSource = allSources.find((s) => s.id === activeSourceId) || selectedSource

  const buffered = useMemo(() => {
    if (!open || buffer <= 0 || !feature?.geometry) return null
    try {
      return turf.buffer(feature, buffer, { units: "meters" })
    } catch {
      return null
    }
  }, [feature, buffer, open])

  const region = useMemo(() => {
    if (!open || !feature?.geometry) return null
    if (buffer > 0 && buffered) return buffered
    return feature
  }, [feature, buffer, buffered, open])

  // COG URL from the active source
  const sourceCogUrl = useMemo(() => {
    const url = activeSource.tileUrl
    if (!url) return null
    const m = url.match(/[?&]url=([^&]+)/)
    return m ? decodeURIComponent(m[1]) : null
  }, [activeSource])

  // TiTiler tile URL with geojson clipping (only for COG sources)
  const cogTileUrl = useMemo(() => {
    if (!sourceCogUrl || !region?.geometry) return null
    const geojson = JSON.stringify(region.geometry)
    return `/cog/tiles/{z}/{x}/{y}.png?url=${encodeURIComponent(sourceCogUrl)}&geojson=${encodeURIComponent(geojson)}`
  }, [sourceCogUrl, region])

  const regionBbox = useMemo(() => {
    return region ? computeBbox(region) : [37, -4, 38, 4]
  }, [region])

  const cropParams = useMemo(() => {
    if (!sourceCogUrl || !open) return null
    const p = new URLSearchParams()
    p.set("url", sourceCogUrl)
    if (region?.geometry) {
      p.set("bbox", turf.bbox(region).join(","))
    }
    return p
  }, [sourceCogUrl, region, open])

  const resetMap = useCallback(() => {
    if (mapRef.current) {
      mapRef.current.remove()
      mapRef.current = null
    }
    mapReady.current = false
  }, [])

  useEffect(() => {
    if (!open) {
      resetMap()
      setBuffer(0)
      setDownloading(null)
      return
    }
    setBuffer(0)
  }, [open, resetMap])

  // Helper to add/remove COG tile layer
  const syncCogLayer = useCallback((m: maplibregl.Map) => {
    if (m.getLayer("cog-tiles-layer")) {
      m.removeLayer("cog-tiles-layer")
      m.removeSource("cog-tiles")
    }
    if (cogTileUrl) {
      m.addSource("cog-tiles", { type: "raster", tiles: [cogTileUrl], tileSize: 256 })
      m.addLayer({ id: "cog-tiles-layer", type: "raster", source: "cog-tiles" })
    }
  }, [cogTileUrl])

  // Initialize map
  useEffect(() => {
    if (!open || !mapContainer.current || mapReady.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: { version: 8, sources: {}, layers: [] },
      center: [(regionBbox[0] + regionBbox[2]) / 2, (regionBbox[1] + regionBbox[3]) / 2],
      zoom: 6,
      attributionControl: false,
    })

    m.on("load", () => {
      // Layer 1 (bottom): OSM reference tiles everywhere
      m.addSource("base-tiles", { type: "raster", tiles: [OSM_TILES], tileSize: 256 })
      m.addLayer({ id: "base-tiles-layer", type: "raster", source: "base-tiles" })

      // Layer 2: COG tiles clipped to polygon (TiTiler returns transparent pixels outside)
      syncCogLayer(m)

      // Layer 3: Selected polygon fill + outline
      m.addSource("selected-polygon", { type: "geojson", data: feature })
      m.addLayer({
        id: "selected-polygon-fill",
        type: "fill",
        source: "selected-polygon",
        paint: { "fill-color": "#3b82f6", "fill-opacity": 0.15, "fill-outline-color": "#2563eb" },
      })
      m.addLayer({
        id: "selected-polygon-line",
        type: "line",
        source: "selected-polygon",
        paint: { "line-color": "#2563eb", "line-width": 2, "line-opacity": 0.9 },
      })

      // Layer 4: Buffer outline
      if (buffer > 0 && buffered) {
        m.addSource("buffer-polygon", { type: "geojson", data: buffered })
        m.addLayer({
          id: "buffer-polygon-line",
          type: "line",
          source: "buffer-polygon",
          paint: { "line-color": "#f59e0b", "line-width": 2, "line-opacity": 0.8, "line-dasharray": [5, 5] },
        })
      }

      m.fitBounds([[regionBbox[0], regionBbox[1]], [regionBbox[2], regionBbox[3]]], { padding: 40 })
      mapReady.current = true
    })

    mapRef.current = m

    return () => {
      m.remove()
      mapRef.current = null
      mapReady.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Sync COG layer when source or buffer changes
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return
    syncCogLayer(m)
  }, [cogTileUrl, syncCogLayer])

  // Update buffer outline + fit bounds
  useEffect(() => {
    const m = mapRef.current
    if (!m || !mapReady.current) return

    if (m.getLayer("buffer-polygon-line")) {
      m.removeLayer("buffer-polygon-line")
      m.removeSource("buffer-polygon")
    }
    if (buffer > 0 && buffered) {
      m.addSource("buffer-polygon", { type: "geojson", data: buffered })
      m.addLayer({
        id: "buffer-polygon-line",
        type: "line",
        source: "buffer-polygon",
        paint: { "line-color": "#f59e0b", "line-width": 2, "line-opacity": 0.8, "line-dasharray": [5, 5] },
      })
    }

    m.fitBounds([[regionBbox[0], regionBbox[1]], [regionBbox[2], regionBbox[3]]], { padding: 40 })
  }, [buffer, buffered, regionBbox])

  const download = async (format: "tif" | "png" | "jpg") => {
    if (!cropParams) return
    setDownloading(format)
    try {
      const ext = format === "tif" ? "tif" : format === "png" ? "png" : "jpg"
      const url = `/cog/crop.${ext}?${cropParams.toString()}`
      const a = document.createElement("a")
      a.href = url
      a.download = `${name.replace(/\s+/g, "_")}_${level}_buffer_${buffer}m.${ext}`
      a.click()
    } catch {
      const url = `/cog/crop.${format === "tif" ? "tif" : format === "png" ? "png" : "jpg"}?${cropParams.toString()}`
      window.open(url, "_blank")
    } finally {
      setDownloading(null)
    }
  }

  const openTitilerViewer = () => {
    if (!sourceCogUrl) return
    window.open(`${TITILER_URL}/viewer?url=${encodeURIComponent(sourceCogUrl)}`, "_blank")
  }

  const exportFromMap = (format: "png" | "jpg") => {
    const m = mapRef.current
    if (!m) return
    const canvas = m.getCanvas()
    const link = document.createElement("a")
    link.download = `${name.replace(/\s+/g, "_")}_${level}_buffer_${buffer}m.${format}`
    if (format === "jpg") {
      link.href = canvas.toDataURL("image/jpeg", 0.92)
    } else {
      link.href = canvas.toDataURL("image/png")
    }
    link.click()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 flex h-[90vh] w-full max-w-5xl flex-col rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold">{name}</h2>
            <p className="text-xs text-gray-500">{level.toUpperCase()} &mdash; Buffer: {buffer}m</p>
          </div>
          <button onClick={onClose} className="rounded p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Buffer control */}
        <div className="flex items-center gap-4 border-b px-6 py-3">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-600">Buffer:</label>
            <input
              type="range"
              min={0}
              max={5000}
              step={100}
              value={buffer}
              onChange={(e) => setBuffer(Number(e.target.value))}
              className="w-32"
            />
            <span className="w-16 text-right text-xs text-gray-500">{buffer}m</span>
          </div>
        </div>

        {/* Map — OSM everywhere + COG clipped to polygon */}
        <div className="flex-1">
          <div ref={mapContainer} className="h-full w-full" />
        </div>

        {/* Footer — source selector + download buttons */}
        <div className="flex items-center justify-between border-t px-6 py-3">
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-600">Source for export:</label>
            <select
              value={activeSourceId}
              onChange={(e) => setActiveSourceId(e.target.value)}
              className="rounded border border-gray-300 px-2 py-1 text-sm"
            >
              {allSources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-2">
            {sourceCogUrl ? (
              <>
                <button
                  onClick={openTitilerViewer}
                  className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
                >
                  View in TiTiler
                </button>
                <button
                  onClick={() => download("tif")}
                  disabled={downloading !== null}
                  className="rounded bg-blue-600 px-3 py-1.5 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  {downloading === "tif" ? "Downloading..." : "GeoTIFF"}
                </button>
              </>
            ) : (
              <span className="text-xs text-amber-600">
                Upload imagery to enable satellite overlay &amp; GeoTIFF
              </span>
            )}
            <button
              onClick={() => exportFromMap("png")}
              className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
            >
              PNG
            </button>
            <button
              onClick={() => exportFromMap("jpg")}
              className="rounded border border-gray-300 px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50"
            >
              JPEG
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
