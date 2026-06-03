"use client"

import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"

import type { ImagerySource } from "@/types/polygon"
import { IMAGERY_SOURCES } from "@/types/polygon"

interface MapViewProps {
  onPolygonDraw?: (geometry: number[][][]) => void
  highlightPolygon?: number[][][] | null
  className?: string
  imagerySource?: ImagerySource
}

export default function MapView({
  onPolygonDraw,
  highlightPolygon,
  className = "",
  imagerySource = IMAGERY_SOURCES[0],
}: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const drawingRef = useRef(false)
  const [drawing, setDrawing] = useState(false)
  const [points, setPoints] = useState<[number, number][]>([])
  const { tileUrl, attribution } = imagerySource

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          "base-tiles": {
            type: "raster",
            tiles: [tileUrl],
            tileSize: 256,
            attribution,
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

    m.on("click", (e) => {
      if (!drawingRef.current) return
      setPoints((prev) => [...prev, [e.lngLat.lng, e.lngLat.lat]])
    })

    map.current = m

    return () => {
      m.remove()
      map.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    drawingRef.current = drawing
  }, [drawing])

  useEffect(() => {
    if (!map.current) return
    const m = map.current
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
  }, [tileUrl, attribution])

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
