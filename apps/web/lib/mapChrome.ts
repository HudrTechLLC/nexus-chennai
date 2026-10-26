import type { Map as MapLibreMap } from "maplibre-gl";

/**
 * Start the compact attribution collapsed (the (i) button still opens it). MapLibre expands it on wide maps,
 * where it covers the bottom of the map on camera (G7). Same rule AreaMap and HexPicker already used.
 */
export function collapseAttribution(m: MapLibreMap, container: HTMLElement | null): void {
  const collapse = () => container?.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  if (m.loaded()) collapse();
  else m.once("load", collapse);
}
