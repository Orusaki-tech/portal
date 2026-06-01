"use client"

import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"

interface MapViewProps {
  onPolygonDraw?: (geometry: number[][][]) => void
  highlightPolygon?: number[][][] | null
  className?: string
}

const NAIP_TILE_URL =
  "https://tiles.planet.com/basemaps/v1/planet-tiles/global_quarterly_2024q1mosaic/gmap/{z}/{x}/{y}.png?api_key=DEMO_API_KEY"

export default function MapView({
  onPolygonDraw,
  highlightPolygon,
  className = "",
}: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [points, setPoints] = useState<[number, number][]>([])

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          "naip-tiles": {
            type: "raster",
            tiles: [NAIP_TILE_URL],
            tileSize: 256,
          },
        },
        layers: [
          {
            id: "naip-tiles-layer",
            type: "raster",
            source: "naip-tiles",
            minzoom: 0,
            maxzoom: 20,
          },
        ],
      },
      center: [-98.0, 39.0],
      zoom: 4,
    })

    m.on("click", (e) => {
      if (!drawing) return
      setPoints((prev) => [...prev, [e.lngLat.lng, e.lngLat.lat]])
    })

    map.current = m

    return () => {
      m.remove()
      map.current = null
    }
  }, [drawing])

  useEffect(() => {
    if (!map.current) return
    const m = map.current

    if (points.length < 3) {
      if (m.getSource("drawing-line")) {
        m.removeLayer("drawing-line-layer")
        m.removeSource("drawing-line")
      }
      return
    }

    const coords = [...points, points[0]]
    const lineGeoJSON: GeoJSON.Feature = {
      type: "Feature",
      properties: {},
      geometry: { type: "LineString", coordinates: coords },
    }

    if (m.getSource("drawing-line")) {
      ;(m.getSource("drawing-line") as maplibregl.GeoJSONSource).setData(
        lineGeoJSON
      )
    } else {
      m.addSource("drawing-line", { type: "geojson", data: lineGeoJSON })
      m.addLayer({
        id: "drawing-line-layer",
        type: "line",
        source: "drawing-line",
        paint: { "line-color": "#ff4500", "line-width": 3 },
      })
    }
  }, [points])

  useEffect(() => {
    if (!map.current || !highlightPolygon) return
    const m = map.current

    const polygonGeoJSON: GeoJSON.Feature = {
      type: "Feature",
      properties: {},
      geometry: { type: "Polygon", coordinates: highlightPolygon },
    }

    if (m.getSource("highlight-polygon")) {
      ;(
        m.getSource("highlight-polygon") as maplibregl.GeoJSONSource
      ).setData(polygonGeoJSON)
    } else {
      m.addSource("highlight-polygon", {
        type: "geojson",
        data: polygonGeoJSON,
      })
      m.addLayer({
        id: "highlight-polygon-layer",
        type: "fill",
        source: "highlight-polygon",
        paint: {
          "fill-color": "#ffff00",
          "fill-opacity": 0.3,
          "fill-outline-color": "#ff0000",
        },
      })
    }

    // Fit map to polygon bounds
    const bounds = new maplibregl.LngLatBounds()
    highlightPolygon[0].forEach(([lng, lat]) => bounds.extend([lng, lat]))
    m.fitBounds(bounds, { padding: 50 })
  }, [highlightPolygon])

  const handleFinishDrawing = () => {
    if (points.length < 3) return
    const geometry = [points]
    onPolygonDraw?.(geometry)
    setPoints([])
    setDrawing(false)
  }

  const handleCancelDrawing = () => {
    if (!map.current) return
    const m = map.current
    if (m.getSource("drawing-line")) {
      m.removeLayer("drawing-line-layer")
      m.removeSource("drawing-line")
    }
    setPoints([])
    setDrawing(false)
  }

  return (
    <div className={`relative ${className}`}>
      <div ref={mapContainer} className="h-full w-full" />

      {/* Controls */}
      <div className="absolute top-4 left-4 z-10 flex gap-2">
        {!drawing ? (
          <button
            onClick={() => setDrawing(true)}
            className="rounded bg-blue-600 px-3 py-2 text-sm text-white shadow hover:bg-blue-700"
          >
            Draw Polygon
          </button>
        ) : (
          <>
            <button
              onClick={handleFinishDrawing}
              className="rounded bg-green-600 px-3 py-2 text-sm text-white shadow hover:bg-green-700"
            >
              Finish ({points.length} pts)
            </button>
            <button
              onClick={handleCancelDrawing}
              className="rounded bg-gray-600 px-3 py-2 text-sm text-white shadow hover:bg-gray-700"
            >
              Cancel
            </button>
          </>
        )}
      </div>

      {drawing && (
        <div className="absolute bottom-4 left-4 z-10 rounded bg-black/70 px-3 py-2 text-sm text-white">
          Click on the map to place vertices. Click &quot;Finish&quot; to complete.
        </div>
      )}
    </div>
  )
}
