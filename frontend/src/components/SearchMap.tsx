"use client";

// Map view of search results (R4). Leaflet + OSM tiles, loaded only on the map view through
// `SearchMapLoader`, so list pages ship no map code (Principle VI).
import "leaflet/dist/leaflet.css";
import type { LatLngBoundsExpression, Map as LeafletMap } from "leaflet";
import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { CircleMarker, MapContainer, Popup, TileLayer, useMap, useMapEvents } from "react-leaflet";
import { Link, useRouter } from "@/i18n/navigation";
import { withParams, type Pair } from "@/lib/search";

export type MapItem = {
  id: string;
  title: string;
  lat: number;
  lng: number;
  price: string;
  href: string;
};

type Props = { items: MapItem[]; bbox?: string; tileUrl: string; attribution: string };

const TANZANIA: LatLngBoundsExpression = [
  [-11.75, 29.3],
  [-0.95, 40.5],
];

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

function parseBbox(bbox?: string): LatLngBoundsExpression | null {
  const parts = bbox?.split(",").map(Number);
  if (!parts || parts.length !== 4 || parts.some(Number.isNaN)) return null;
  const [minLng, minLat, maxLng, maxLat] = parts;
  return [
    [minLat, minLng],
    [maxLat, maxLng],
  ];
}

/** Fits the view once, then searches the visible area whenever the visitor moves the map. */
function Viewport({ items, bbox }: { items: MapItem[]; bbox?: string }) {
  const map = useMap();
  const router = useRouter();
  const search = useSearchParams();
  // Only moves that follow a gesture on the map search; fitting the view (which may fire
  // zero or several `moveend`s) never does.
  const touched = useRef(false);

  useEffect(() => {
    const fromUrl = parseBbox(bbox);
    const fromItems: LatLngBoundsExpression | null = items.length
      ? items.map((i) => [i.lat, i.lng] as [number, number])
      : null;
    map.fitBounds(fromUrl ?? fromItems ?? TANZANIA, { padding: [24, 24], maxZoom: 14 });

    const container = map.getContainer();
    const gestures = ["pointerdown", "wheel", "keydown", "touchstart"] as const;
    const onGesture = () => {
      touched.current = true;
    };
    gestures.forEach((g) => container.addEventListener(g, onGesture, { passive: true }));
    return () => gestures.forEach((g) => container.removeEventListener(g, onGesture));
    // Runs once: later moves come from the visitor.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  useMapEvents({
    moveend(event) {
      if (!touched.current) return;
      const b = (event.target as LeafletMap).getBounds();
      const box = [
        clamp(b.getWest(), -180, 180),
        clamp(b.getSouth(), -90, 90),
        clamp(b.getEast(), -180, 180),
        clamp(b.getNorth(), -90, 90),
      ]
        .map((v) => v.toFixed(5))
        .join(",");
      const pairs = Array.from(search.entries()) as Pair[];
      router.replace(`/search${withParams(pairs, { bbox: box })}`, { scroll: false });
    },
  });
  return null;
}

export default function SearchMap({ items, bbox, tileUrl, attribution }: Props) {
  return (
    <MapContainer
      bounds={TANZANIA}
      scrollWheelZoom={false}
      className="h-[60vh] w-full rounded-xl border border-line"
    >
      <TileLayer url={tileUrl} attribution={attribution} />
      <Viewport items={items} bbox={bbox} />
      {items.map((item) => (
        <CircleMarker
          key={item.id}
          center={[item.lat, item.lng]}
          radius={9}
          pathOptions={{ color: "#115e59", fillColor: "#0f766e", fillOpacity: 0.85, weight: 2 }}
        >
          <Popup>
            <Link href={item.href} className="font-semibold text-brand-700">
              {item.title}
            </Link>
            <br />
            {item.price}
          </Popup>
        </CircleMarker>
      ))}
    </MapContainer>
  );
}
