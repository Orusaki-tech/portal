"use client"

import { useEffect, useRef } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import type { ImagerySource, ParsedGeometry } from "@/types/polygon"

interface DatasetPreviewMapProps {
  geometries: ParsedGeometry[]
  imagerySource: ImagerySource | null
  className?: string
}

export default function DatasetPreviewMap({
  geometries,
  imagerySource,
  className = "",
}: DatasetPreviewMapProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)

  const tileUrl = imagerySource?.tileUrl
  const attribution = imagerySource?.attribution

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          "base-tiles": {
            type: "raster",
            tiles: [tileUrl || "https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: attribution || "OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "base-tiles-layer",
            type: "raster",
            source: "base-tiles",
            minzoom: 0,
            maxzoom: 20,
          },
        ],
      },
      center: [-98.0, 39.0],
      zoom: 4,
    })

    m.addControl(new maplibregl.NavigationControl(), "top-right")

    map.current = m

    return () => {
      m.remove()
      map.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return

    if (tileUrl && m.getLayer("base-tiles-layer")) {
      m.removeLayer("base-tiles-layer")
      m.removeSource("base-tiles")

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
    if (!m) return

    if (!m.loaded()) {
      m.on("load", () => updatePolygons(m, geometries))
      return
    }

    updatePolygons(m, geometries)
  }, [geometries])

  return (
    <div className={`relative ${className}`}>
      <div ref={mapContainer} className="h-full w-full rounded-lg border" />
      {geometries.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center rounded-lg bg-gray-100/80">
          <p className="text-sm text-gray-500">
            Upload a dataset to preview polygons
          </p>
        </div>
      )}
      {!imagerySource && geometries.length > 0 && (
        <div className="absolute top-2 left-2 z-10 rounded bg-yellow-100 px-2 py-1 text-xs text-yellow-700">
          No imagery selected — showing OSM reference
        </div>
      )}
    </div>
  )
}

function updatePolygons(m: maplibregl.Map, geometries: ParsedGeometry[]) {
  if (m.getLayer("polygons-fill")) {
    m.removeLayer("polygons-fill")
    m.removeLayer("polygons-outline")
    m.removeSource("polygons")
  }

  if (geometries.length === 0) return

  const features = geometries.map((g) => ({
    type: "Feature" as const,
    properties: {
      id: g.id,
      status: g.status,
    },
    geometry: {
      type: "Polygon" as const,
      coordinates: g.coords,
    },
  }))

  const geojson: GeoJSON.FeatureCollection = {
    type: "FeatureCollection",
    features,
  }

  m.addSource("polygons", { type: "geojson", data: geojson })

  m.addLayer({
    id: "polygons-fill",
    type: "fill",
    source: "polygons",
    paint: {
      "fill-color": [
        "match",
        ["get", "status"],
        "valid",
        "#22c55e",
        "warning",
        "#eab308",
        "error",
        "#ef4444",
        "#94a3b8",
      ],
      "fill-opacity": 0.25,
    },
  })

  m.addLayer({
    id: "polygons-outline",
    type: "line",
    source: "polygons",
    paint: {
      "line-color": [
        "match",
        ["get", "status"],
        "valid",
        "#16a34a",
        "warning",
        "#ca8a04",
        "error",
        "#dc2626",
        "#64748b",
      ],
      "line-width": 1.5,
    },
  })

  const bounds = new maplibregl.LngLatBounds()
  for (const g of geometries) {
    for (const coord of g.coords[0]) {
      bounds.extend(coord as [number, number])
    }
  }

  if (!bounds.isEmpty()) {
    m.fitBounds(bounds, { padding: 40, maxZoom: 16 })
  }
}
