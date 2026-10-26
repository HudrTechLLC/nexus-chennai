"use client";
import { ScatterplotLayer } from "@deck.gl/layers";
import { MapCanvas } from "@/components/console/map/MapCanvas";
import { CITY } from "@/lib/city";

/** Click the map to set the scene of the crime (G4 "map picker"). Browser only: load with next/dynamic. */
export default function PlacePicker({ lat, lon, onPick, home }: {
  lat: number | null; lon: number | null; onPick: (lat: number, lon: number) => void;
  /** Where to open when nothing is picked yet: the officer's station centroid [lon, lat]. */
  home?: [number, number] | null;
}) {
  const point = lat !== null && lon !== null ? [{ p: [lon, lat] as [number, number] }] : [];
  const layers = [
    new ScatterplotLayer<{ p: [number, number] }>({
      id: "fir-place",
      data: point,
      getPosition: (d) => d.p,
      getRadius: 9,
      radiusUnits: "pixels",
      getFillColor: [230, 57, 70, 230],
      getLineColor: [255, 255, 255, 255],
      lineWidthMinPixels: 2,
      stroked: true,
    }),
  ];
  return (
    <div className="h-72 overflow-hidden rounded-lg border border-line">
      <MapCanvas
        view={{
          center: lon !== null && lat !== null ? [lon, lat] : home ?? CITY.map.center,
          zoom: lat !== null ? 14 : home ? 13 : CITY.map.zoom,
          bounds: CITY.map.bounds,
        }}
        layers={layers}
        theme="light"
        onClick={(info) => {
          if (info.coordinate) onPick(Number(info.coordinate[1].toFixed(6)), Number(info.coordinate[0].toFixed(6)));
        }}
      />
    </div>
  );
}
