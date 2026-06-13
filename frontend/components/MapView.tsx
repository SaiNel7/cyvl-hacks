"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import Map, { useControl, type MapRef } from "react-map-gl/maplibre";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer, PointCloudLayer } from "@deck.gl/layers";
import { COORDINATE_SYSTEM } from "@deck.gl/core";
import type { MapboxOverlayProps } from "@deck.gl/mapbox";
import useSWR from "swr";
import "maplibre-gl/dist/maplibre-gl.css";

import { fetcher } from "@/lib/fetcher";
import { useAppStore } from "@/lib/store";
import {
  adjustedScore,
  geoJsonToSpots,
  scoreToColor,
} from "@/lib/scoring";
import { buildSpotsUrl } from "@/lib/spots-url";
import type { Spot, SpotsGeoJSON, Voxel } from "@/lib/types";

const MAP_STYLE =
  "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json";

const INITIAL_VIEW = {
  longitude: -71.1,
  latitude: 42.39,
  zoom: 13.5,
  pitch: 50,
  bearing: -20,
};

function DeckGLOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

function polygonCentroid(spot: Spot): [number, number] {
  const ring = spot.geometry.coordinates[0];
  const lng = ring.reduce((sum, c) => sum + c[0], 0) / ring.length;
  const lat = ring.reduce((sum, c) => sum + c[1], 0) / ring.length;
  return [lng, lat];
}

export function MapView() {
  const mapRef = useRef<MapRef>(null);
  const filters = useAppStore((s) => s.filters);
  const selectedSpotId = useAppStore((s) => s.selectedSpotId);
  const setSelectedSpotId = useAppStore((s) => s.setSelectedSpotId);

  const { data } = useSWR<SpotsGeoJSON>(buildSpotsUrl(filters), fetcher);
  const spots = useMemo(() => (data ? geoJsonToSpots(data) : []), [data]);

  // Only the clicked wall's 3D point cloud is fetched/rendered — not all of them.
  // A 404 (wall not voxelized yet) is swallowed so pins keep working.
  const { data: voxels } = useSWR<Voxel[]>(
    selectedSpotId ? `/api/walls/${selectedSpotId}/voxels` : null,
    fetcher,
    { shouldRetryOnError: false }
  );

  const layers = useMemo(() => {
    if (spots.length === 0) return [];

    // Default view: a score-colored pin per surface. The real 3D wall only
    // appears once you click in.
    const pins = new ScatterplotLayer<Spot>({
      id: "spot-pins",
      data: spots,
      pickable: true,
      autoHighlight: true,
      highlightColor: [255, 214, 0, 220],
      stroked: true,
      lineWidthMinPixels: 2,
      getLineColor: [0, 0, 0, 255],
      radiusUnits: "pixels",
      getPosition: (d) => polygonCentroid(d),
      getRadius: (d) => (selectedSpotId === d.id ? 11 : 8),
      getFillColor: (d) => {
        const score = adjustedScore(d, filters.timeOfDay);
        const alpha = selectedSpotId && selectedSpotId !== d.id ? 110 : 240;
        return scoreToColor(score, alpha);
      },
      onClick: ({ object }) => {
        if (object) setSelectedSpotId(object.id);
      },
      updateTriggers: {
        getFillColor: [filters.timeOfDay, selectedSpotId],
        getRadius: [selectedSpotId],
      },
    });

    if (!voxels || voxels.length === 0) return [pins];

    // The actual building wall: real-color lidar voxels floating at their true
    // lon/lat and height above ground.
    const cloud = new PointCloudLayer<Voxel>({
      id: `wall-voxels-${selectedSpotId}`,
      data: voxels,
      coordinateSystem: COORDINATE_SYSTEM.LNGLAT,
      getPosition: (d) => [d.lon, d.lat, d.z],
      getColor: (d) => [d.r, d.g, d.b],
      pointSize: 4,
      sizeUnits: "pixels",
      material: false,
      pickable: false,
    });

    return [pins, cloud];
  }, [spots, voxels, filters.timeOfDay, selectedSpotId, setSelectedSpotId]);

  const flyToSpot = useCallback((spot: Spot) => {
    const [lng, lat] = polygonCentroid(spot);
    mapRef.current?.flyTo({
      center: [lng, lat],
      zoom: 16.5,
      pitch: 55,
      bearing: -15,
      duration: 200,
      essential: true,
    });
  }, []);

  useEffect(() => {
    if (!selectedSpotId) return;
    const spot = spots.find((s) => s.id === selectedSpotId);
    if (spot) flyToSpot(spot);
  }, [selectedSpotId, spots, flyToSpot]);

  return (
    <div className="relative h-full w-full bg-brut-white">
      <Map
        ref={mapRef}
        initialViewState={INITIAL_VIEW}
        mapStyle={MAP_STYLE}
        style={{ width: "100%", height: "100%" }}
        attributionControl={false}
      >
        <DeckGLOverlay layers={layers} interleaved />
      </Map>

      <div className="pointer-events-none absolute bottom-4 left-4 max-w-xs brut-border brut-shadow bg-brut-white px-4 py-3">
        <p className="text-sm font-extrabold uppercase tracking-tight">
          LiDAR surfaces
        </p>
        <div className="mt-2 space-y-1.5 text-xs font-bold">
          <p className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 shrink-0 border-2 border-black bg-brut-green" />
            Green ≥85
          </p>
          <p className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 shrink-0 border-2 border-black bg-brut-yellow" />
            Yellow 60–84
          </p>
          <p className="flex items-center gap-2">
            <span className="inline-block h-3 w-3 shrink-0 border-2 border-black bg-brut-pink" />
            Pink &lt;60
          </p>
        </div>
      </div>
    </div>
  );
}
