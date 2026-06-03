"use client"

import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"

import { wktToCoords } from "@/lib/wkt"
import { IMAGERY_SOURCES } from "@/types/polygon"

interface GridBlock {
  grid_id: string
  geometry: string
  status: string
  assigned_user_id?: string | null
  polygon_count: number
}

interface GridBlockMapProps {
  grids: GridBlock[]
  className?: string
}

const SOURCE_ID = "grid-blocks"
const FILL_LAYER_ID = "grid-blocks-fill"
const OUTLINE_LAYER_ID = "grid-blocks-outline"

export default function GridBlockMap({ grids, className = "" }: GridBlockMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const gridsRef = useRef(grids)
  const [selectedGrid, setSelectedGrid] = useState<GridBlock | null>(null)

  gridsRef.current = grids

  const source = IMAGERY_SOURCES[0]
  const tileUrl = source.tileUrl
  const attribution = source.attribution

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          "base-tiles": { type: "raster", tiles: [tileUrl], tileSize: 256, attribution },
        },
        layers: [
          { id: "base-tiles-layer", type: "raster", source: "base-tiles", minzoom: 0, maxzoom: 20 },
        ],
      },
      center: [-98.0, 39.0],
      zoom: 4,
    })

    m.addControl(new maplibregl.NavigationControl(), "top-right")

    m.on("click", FILL_LAYER_ID, (e) => {
      if (e.features && e.features[0]) {
        const props = e.features[0].properties as Record<string, unknown>
        const found = gridsRef.current.find((g) => g.grid_id === props.grid_id)
        if (found) setSelectedGrid(found)
      }
    })

    m.on("click", (e) => {
      const features = m.queryRenderedFeatures(e.point, { layers: [FILL_LAYER_ID] })
      if (features.length === 0) setSelectedGrid(null)
    })

    map.current = m

    return () => { m.remove(); map.current = null }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (tileUrl || attribution) {
      const m = map.current
      if (!m) return
      if (m.getLayer("base-tiles-layer")) {
        m.removeLayer("base-tiles-layer")
        m.removeSource("base-tiles")
      }
      m.addSource("base-tiles", {
        type: "raster",
        tiles: [tileUrl],
        tileSize: 256,
      })
      m.addLayer({
        id: "base-tiles-layer",
        type: "raster",
        source: "base-tiles",
        minzoom: 0,
        maxzoom: 20,
      })
    }
  }, [tileUrl, attribution])

  useEffect(() => {
    const m = map.current
    if (!m || !m.loaded()) {
      const onLoad = () => { updateGridBlocks(m!, gridsRef.current) }
      if (m) { m.on("load", onLoad); return () => { void m.off("load", onLoad) } }
      return
    }
    updateGridBlocks(m, gridsRef.current)
  }, [grids])

  const statusColor = (status: string) => {
    switch (status) {
      case "available": return "bg-green-100 text-green-800"
      case "locked": return "bg-yellow-100 text-yellow-800"
      case "completed": return "bg-blue-100 text-blue-800"
      case "verified": return "bg-purple-100 text-purple-800"
      default: return "bg-gray-100 text-gray-800"
    }
  }

  return (
    <div className={`relative ${className}`}>
      <div ref={mapContainer} className="h-80 w-full rounded-lg border" />

      <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-600">
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-green-400" /> Available
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-yellow-400" /> Locked
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-blue-400" /> Completed
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-3 w-3 rounded bg-purple-400" /> Verified
        </span>
      </div>

      {selectedGrid && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-3">
          <p className="text-sm font-medium">Grid Block</p>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
            <span>Status: <span className={`rounded px-1.5 py-0.5 font-medium ${statusColor(selectedGrid.status)}`}>{selectedGrid.status}</span></span>
            <span>Polygons: {selectedGrid.polygon_count}</span>
            {selectedGrid.assigned_user_id && <span>Assigned: {selectedGrid.assigned_user_id.slice(0, 8)}...</span>}
          </div>
        </div>
      )}
    </div>
  )
}

function updateGridBlocks(m: maplibregl.Map, grids: GridBlock[]) {
  const bounds = new maplibregl.LngLatBounds()
  const features: GeoJSON.Feature[] = grids.map((g) => {
    const coords = wktToCoords(g.geometry)
    if (coords) {
      coords[0].forEach((c) => bounds.extend(c as [number, number]))
    }
    return {
      type: "Feature",
      id: g.grid_id,
      properties: { grid_id: g.grid_id, status: g.status, assigned_user_id: g.assigned_user_id, polygon_count: g.polygon_count },
      geometry: { type: "Polygon", coordinates: coords || [] },
    }
  })

  const geojson: GeoJSON.FeatureCollection = { type: "FeatureCollection", features }

  if (m.getSource(SOURCE_ID)) {
    (m.getSource(SOURCE_ID) as maplibregl.GeoJSONSource).setData(geojson)
  } else {
    m.addSource(SOURCE_ID, { type: "geojson", data: geojson })
    m.addLayer({
      id: FILL_LAYER_ID,
      type: "fill",
      source: SOURCE_ID,
      paint: {
        "fill-color": [
          "match", ["get", "status"],
          "available", "#22c55e",
          "locked", "#eab308",
          "completed", "#3b82f6",
          "verified", "#8b5cf6",
          "#94a3b8",
        ],
        "fill-opacity": 0.3,
      },
    })
    m.addLayer({
      id: OUTLINE_LAYER_ID,
      type: "line",
      source: SOURCE_ID,
      paint: { "line-color": "#475569", "line-width": 1.5 },
    })
  }

  if (features.length > 0) {
    m.fitBounds(bounds, { padding: 40 })
  }
}
