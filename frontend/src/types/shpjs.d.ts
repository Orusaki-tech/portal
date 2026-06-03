declare module "shpjs" {
  interface ShapefileFeature {
    type: "Point" | "Polygon" | "MultiPolygon" | "LineString"
    coordinates: number[] | number[][] | number[][][] | number[][][][]
    properties: Record<string, unknown>
  }

  export default function parse(
    data: ArrayBuffer
  ): Promise<ShapefileFeature[] | ShapefileFeature>
}
