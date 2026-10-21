"use client";

// Map pin for a listing (optional): click or tap to place it. Leaflet + OSM tiles, loaded
// on the client only through `LocationPinMapLoader`.
import "leaflet/dist/leaflet.css";
import type { LatLngBoundsExpression } from "leaflet";
import { CircleMarker, MapContainer, TileLayer, useMapEvents } from "react-leaflet";

const TANZANIA: LatLngBoundsExpression = [
  [-11.75, 29.3],
  [-0.95, 40.5],
];

type Point = { lat: number; lng: number };
type Props = {
  value: Point | null;
  onChange: (point: Point) => void;
  tileUrl: string;
  attribution: string;
};

function ClickToPlace({ onChange }: { onChange: (point: Point) => void }) {
  useMapEvents({
    click(e) {
      onChange({ lat: Number(e.latlng.lat.toFixed(6)), lng: Number(e.latlng.lng.toFixed(6)) });
    },
  });
  return null;
}

export default function LocationPinMap({ value, onChange, tileUrl, attribution }: Props) {
  return (
    <MapContainer
      bounds={TANZANIA}
      center={value ? [value.lat, value.lng] : undefined}
      zoom={value ? 14 : undefined}
      scrollWheelZoom={false}
      className="h-64 w-full rounded-xl border border-line"
    >
      <TileLayer url={tileUrl} attribution={attribution} />
      <ClickToPlace onChange={onChange} />
      {value && (
        <CircleMarker
          center={[value.lat, value.lng]}
          radius={10}
          pathOptions={{ color: "#115e59", fillColor: "#0f766e", fillOpacity: 0.85, weight: 2 }}
        />
      )}
    </MapContainer>
  );
}
