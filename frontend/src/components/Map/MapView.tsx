"use client"

import { useEffect, useRef, useState } from "react"
import maplibregl from "maplibre-gl"
import "maplibre-gl/dist/maplibre-gl.css"
import type { ImagerySource, AdminLevel, VectorOverlay } from "@/types/polygon"
import { IMAGERY_SOURCES } from "@/types/polygon"

interface AdminData {
  level: AdminLevel
  data: GeoJSON.FeatureCollection
}

interface MapViewProps {
  onPolygonDraw?: (geometry: number[][][]) => void
  highlightPolygon?: number[][][] | null
  className?: string
  imagerySource?: ImagerySource
  adminData?: AdminData[]
  selectedAdminId?: string | null
  hoveredAdminId?: string | null
  onAdminSelect?: (id: string, level: AdminLevel, feature: GeoJSON.Feature) => void
  onAdminHover?: (id: string | null, level: AdminLevel | null) => void
  onRequestImagery?: (id: string, level: AdminLevel, feature: GeoJSON.Feature) => void
  overlays?: VectorOverlay[]
}

function getProp(feature: GeoJSON.Feature, key: string): string {
  const v = feature.properties?.[key]
  return v != null ? String(v) : ""
}

function getPcode(level: AdminLevel, feature: GeoJSON.Feature): string {
  if (level === "admin0") return getProp(feature, "adm0_pcode")
  if (level === "admin1") return getProp(feature, "adm1_pcode")
  return getProp(feature, "adm2_pcode")
}

export default function MapView({
  onPolygonDraw,
  highlightPolygon,
  className = "",
  imagerySource = IMAGERY_SOURCES[0],
  adminData = [],
  selectedAdminId,
  hoveredAdminId,
  onAdminSelect,
  onAdminHover,
  onRequestImagery,
  overlays = [],
}: MapViewProps) {
  const mapContainer = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const loaded = useRef(false)
  const drawingRef = useRef(false)
  const popup = useRef<maplibregl.Popup | null>(null)
  const [drawing, setDrawing] = useState(false)
  const [points, setPoints] = useState<[number, number][]>([])
  const { tileUrl, attribution } = imagerySource
  const prevSelectedRef = useRef<string | null>(null)
  const adminAddedRef = useRef(false)
  const adminFeaturesRef = useRef<Map<string, { feature: GeoJSON.Feature; level: AdminLevel }>>(new Map())
  const hoveredRef = useRef<string | null>(null)

  useEffect(() => {
    if (!mapContainer.current || map.current) return

    const m = new maplibregl.Map({
      container: mapContainer.current,
      style: { version: 8, sources: {}, layers: [] },
      center: [37.55, 0.37],
      zoom: 6,
      maxBounds: [
        [30, -6],
        [45, 6],
      ],
    })

    m.on("load", () => {
      loaded.current = true
      addBaseTiles(m, tileUrl, attribution)
      addAdminLayers(m, adminData, adminFeaturesRef.current)
      adminAddedRef.current = true
    })

    m.on("click", (e) => {
      if (!drawingRef.current) return
      setPoints((prev) => [...prev, [e.lngLat.lng, e.lngLat.lat]])
    })

    m.on("click", (e) => {
      if (drawingRef.current) return
      const features = m.queryRenderedFeatures(e.point, {
        layers: ["admin1-fill", "admin2-fill", "admin0-fill"],
      })
      if (features.length > 0) {
        const feat = features[0]
        const layerId = feat.layer?.id || ""
        const level = layerId.replace("-fill", "") as AdminLevel
        const id = `${level}:${getPcode(level, feat)}`
        const props = feat.properties || {}
        const name = props.adm0_name || props.adm1_name || props.adm2_name || getPcode(level, feat)
        // highlight on click immediately
        onAdminSelect?.(id, level, feat)
        if (popup.current) popup.current.remove()
        popup.current = new maplibregl.Popup({ closeButton: true, closeOnClick: true })
          .setLngLat(e.lngLat)
          .setHTML(
            `<div class="text-sm">
              <p class="font-semibold">${name}</p>
              <p class="text-xs text-gray-500">${level.toUpperCase()} — ${getPcode(level, feat)}</p>
              <button id="get-imagery-btn" class="mt-2 rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700">Get Satellite Imagery</button>
            </div>`
          )
          .addTo(m)
        setTimeout(() => {
          const btn = document.getElementById("get-imagery-btn")
          if (btn) {
            btn.onclick = () => {
              popup.current?.remove()
              onRequestImagery?.(id, level, feat)
            }
          }
        }, 0)
      }
    })

    m.on("mousemove", (e) => {
      if (drawingRef.current) return
      const features = m.queryRenderedFeatures(e.point, {
        layers: ["admin1-fill", "admin2-fill", "admin0-fill"],
      })
      if (features.length > 0) {
        m.getCanvas().style.cursor = "pointer"
        const feat = features[0]
        const layerId = feat.layer?.id || ""
        const level = layerId.replace("-fill", "") as AdminLevel
        const id = `${level}:${getPcode(level, feat)}`
        hoveredRef.current = id
        onAdminHover?.(id, level)
        updateHover(m, id, feat)
      } else {
        m.getCanvas().style.cursor = ""
        if (hoveredRef.current) {
          hoveredRef.current = null
          onAdminHover?.(null, null)
          clearHover(m)
        }
      }
    })

    map.current = m

    return () => {
      m.remove()
      map.current = null
      loaded.current = false
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!map.current || !loaded.current) return
    adminFeaturesRef.current.clear()
    clearAdminLayers(map.current)
    addAdminLayers(map.current, adminData, adminFeaturesRef.current)
    adminAddedRef.current = adminData.length > 0
  }, [adminData])

  useEffect(() => {
    if (!map.current || !loaded.current) return
    const m = map.current
    if (prevSelectedRef.current && m.getSource("admin-select")) {
      ;(m.getSource("admin-select") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: [],
      })
    }
    prevSelectedRef.current = selectedAdminId || null
    if (!selectedAdminId) return
    const match = adminFeaturesRef.current.get(selectedAdminId)
    if (!match) return
    if (m.getSource("admin-select")) {
      ;(m.getSource("admin-select") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: [match.feature],
      })
    } else {
      m.addSource("admin-select", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [match.feature] },
      })
      m.addLayer({
        id: "admin-select-layer",
        type: "fill",
        source: "admin-select",
        paint: {
          "fill-color": "#3b82f6",
          "fill-opacity": 0.25,
          "fill-outline-color": "#2563eb",
        },
      })
      m.addLayer({
        id: "admin-select-outline",
        type: "line",
        source: "admin-select",
        paint: {
          "line-color": "#2563eb",
          "line-width": 3,
          "line-opacity": 0.9,
        },
      })
    }
    const bbox = turfBbox(match.feature)
    if (bbox) {
      const bounds = new maplibregl.LngLatBounds(
        [bbox[0], bbox[1]],
        [bbox[2], bbox[3]]
      )
      m.fitBounds(bounds, { padding: 50 })
    }
  }, [selectedAdminId])

  useEffect(() => {
    if (!map.current || !loaded.current) return
    const m = map.current
    if (hoveredAdminId) {
      const match = adminFeaturesRef.current.get(hoveredAdminId)
      if (match) updateHover(m, hoveredAdminId, match.feature)
    } else {
      clearHover(m)
    }
  }, [hoveredAdminId])

  useEffect(() => {
    drawingRef.current = drawing
  }, [drawing])

  // sync overlay opacity/visibility from panel toggles
  useEffect(() => {
    const m = map.current
    if (!m || !loaded.current) return
    for (const o of overlays) {
      if (o.type !== "admin" || !o.level) continue
      const fill = `${o.level}-fill`
      const line = `${o.level}-line`
      if (!m.getLayer(fill)) continue
      m.setPaintProperty(fill, "fill-opacity", o.visible ? o.opacity : 0)
      if (m.getLayer(line)) {
        m.setPaintProperty(line, "line-opacity", o.visible ? 0.8 : 0)
      }
      m.setLayoutProperty(fill, "visibility", o.visible ? "visible" : "none")
      if (m.getLayer(line)) {
        m.setLayoutProperty(line, "visibility", o.visible ? "visible" : "none")
      }
    }
  }, [overlays])

  useEffect(() => {
    const m = map.current
    if (!m || !loaded.current) return
    removeBaseTiles(m)
    addBaseTiles(m, tileUrl, attribution)
  }, [tileUrl, attribution])

  useEffect(() => {
    const m = map.current
    if (!m || !loaded.current) return
    if (points.length < 3) {
      if (m.getLayer("drawing-line-layer")) {
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
    const m = map.current
    if (!m || !loaded.current || !highlightPolygon) return

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
    if (m.getLayer("drawing-line-layer")) {
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

function turfBbox(feature: GeoJSON.Feature): [number, number, number, number] | null {
  if (feature.geometry?.type === "Polygon") {
    const ring = feature.geometry.coordinates[0]
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const [x, y] of ring) {
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
    return [minX, minY, maxX, maxY]
  }
  if (feature.geometry?.type === "MultiPolygon") {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const polygon of feature.geometry.coordinates) {
      for (const [x, y] of polygon[0]) {
        if (x < minX) minX = x
        if (y < minY) minY = y
        if (x > maxX) maxX = x
        if (y > maxY) maxY = y
      }
    }
    return [minX, minY, maxX, maxY]
  }
  return null
}

function updateHover(m: maplibregl.Map, id: string, feature: GeoJSON.Feature) {
  if (m.getSource("admin-hover")) {
    ;(m.getSource("admin-hover") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: [feature],
    })
  } else {
    m.addSource("admin-hover", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [feature] },
    })
    m.addLayer({
      id: "admin-hover-layer",
      type: "fill",
      source: "admin-hover",
      paint: {
        "fill-color": "#fbbf24",
        "fill-opacity": 0.2,
        "fill-outline-color": "#f59e0b",
      },
    })
  }
}

function clearHover(m: maplibregl.Map) {
  if (m.getLayer("admin-hover-layer")) {
    m.removeLayer("admin-hover-layer")
    m.removeSource("admin-hover")
  }
}

function addBaseTiles(m: maplibregl.Map, tileUrl: string, attribution: string) {
  if (m.getSource("base-tiles")) return
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

function removeBaseTiles(m: maplibregl.Map) {
  if (m.getLayer("base-tiles-layer")) {
    m.removeLayer("base-tiles-layer")
    m.removeSource("base-tiles")
  }
}

function clearAdminLayers(m: maplibregl.Map) {
  const ids = ["admin2-fill", "admin2-line", "admin1-fill", "admin1-line", "admin0-fill", "admin0-line"]
  ids.forEach((id) => {
    if (m.getLayer(id)) {
      try { m.removeLayer(id) } catch {}
    }
  })
  ;["admin2-source", "admin1-source", "admin0-source"].forEach((id) => {
    if (m.getSource(id)) {
      try { m.removeSource(id) } catch {}
    }
  })
}

function addAdminLayers(m: maplibregl.Map, adminData: AdminData[], featureMap?: Map<string, { feature: GeoJSON.Feature; level: AdminLevel }>) {
  for (const adm of adminData) {
    const lvl = adm.level
    const sourceId = `${lvl}-source`
    if (m.getSource(sourceId)) continue
    m.addSource(sourceId, {
      type: "geojson",
      data: adm.data,
    })
  }

  // admin0: country outline
  if (adminData.some((a) => a.level === "admin0") && !m.getLayer("admin0-fill")) {
    m.addLayer({
      id: "admin0-fill",
      type: "fill",
      source: "admin0-source",
      paint: {
        "fill-color": "#e8f5e9",
        "fill-opacity": 0,
      },
    })
    m.addLayer({
      id: "admin0-line",
      type: "line",
      source: "admin0-source",
      paint: {
        "line-color": "#2e7d32",
        "line-width": 2,
        "line-opacity": 0.8,
      },
    })
  }

  // admin1: counties
  if (adminData.some((a) => a.level === "admin1") && !m.getLayer("admin1-fill")) {
    m.addLayer({
      id: "admin1-fill",
      type: "fill",
      source: "admin1-source",
      paint: {
        "fill-color": "#e8edf5",
        "fill-opacity": 0.12,
        "fill-outline-color": "#64748b",
      },
    })
    m.addLayer({
      id: "admin1-line",
      type: "line",
      source: "admin1-source",
      paint: {
        "line-color": "#475569",
        "line-width": 1.5,
        "line-opacity": 0.6,
      },
    })
  }

  // admin2: sub-counties
  if (adminData.some((a) => a.level === "admin2") && !m.getLayer("admin2-fill")) {
    m.addLayer({
      id: "admin2-fill",
      type: "fill",
      source: "admin2-source",
      minzoom: 8,
      paint: {
        "fill-color": "#fafafa",
        "fill-opacity": 0,
        "fill-outline-color": "#cbd5e1",
      },
    })
    m.addLayer({
      id: "admin2-line",
      type: "line",
      source: "admin2-source",
      minzoom: 8,
      paint: {
        "line-color": "#94a3b8",
        "line-width": 0.5,
        "line-opacity": 0.5,
      },
    })
  }

  // populate feature map for lookups
  if (featureMap) {
    for (const adm of adminData) {
      for (const feature of adm.data.features) {
        const pcode = getPcode(adm.level, feature)
        if (pcode) {
          const key = `${adm.level}:${pcode}`
          featureMap.set(key, { feature, level: adm.level })
        }
      }
    }
  }
}
