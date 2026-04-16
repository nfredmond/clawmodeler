from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .workspace import read_json, utc_now


class MapDependencyMissingError(RuntimeError):
    pass


def _require_folium():
    try:
        import folium

        return folium
    except ModuleNotFoundError as error:
        raise MapDependencyMissingError(
            "folium is not installed. Install the standard profile: "
            "`bash scripts/install-profile.sh standard`."
        ) from error


def _geojson_bbox(feature_collection: dict[str, Any]) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = 180.0, 90.0, -180.0, -90.0
    for feature in feature_collection.get("features", []):
        geometry = feature.get("geometry") or {}
        for longitude, latitude in _iter_coords(geometry):
            min_lon = min(min_lon, longitude)
            min_lat = min(min_lat, latitude)
            max_lon = max(max_lon, longitude)
            max_lat = max(max_lat, latitude)
    if min_lon > max_lon or min_lat > max_lat:
        return (-180.0, -90.0, 180.0, 90.0)
    return min_lon, min_lat, max_lon, max_lat


def _iter_coords(geometry: dict[str, Any]):
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if coordinates is None:
        return
    if geometry_type == "Polygon":
        for ring in coordinates:
            yield from ring
    elif geometry_type == "MultiPolygon":
        for polygon in coordinates:
            for ring in polygon:
                yield from ring
    elif geometry_type == "Point":
        yield coordinates
    elif geometry_type == "LineString":
        yield from coordinates
    elif geometry_type == "MultiLineString":
        for line in coordinates:
            yield from line


def _choropleth(
    folium_module,
    zones_geojson: dict[str, Any],
    value_by_zone: dict[str, float],
    *,
    caption: str,
    color_scheme: str = "YlGnBu",
) -> Any:
    min_lon, min_lat, max_lon, max_lat = _geojson_bbox(zones_geojson)
    center = [(min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0]
    map_object = folium_module.Map(location=center, zoom_start=11, control_scale=True)

    data = [
        (str(zone_id), float(value))
        for zone_id, value in value_by_zone.items()
        if value is not None
    ]

    if data:
        folium_module.Choropleth(
            geo_data=zones_geojson,
            data=data,
            columns=["zone_id", "value"],
            key_on="feature.properties.zone_id",
            fill_color=color_scheme,
            fill_opacity=0.75,
            line_opacity=0.4,
            legend_name=caption,
            nan_fill_color="#cccccc",
        ).add_to(map_object)

    folium_module.GeoJson(
        zones_geojson,
        name="Zones",
        style_function=lambda _feature: {
            "color": "#333333",
            "weight": 0.6,
            "fillOpacity": 0.0,
        },
        tooltip=folium_module.GeoJsonTooltip(
            fields=["zone_id"],
            aliases=["Zone:"],
            sticky=True,
        ),
    ).add_to(map_object)

    map_object.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])
    return map_object


def zones_accessibility_map(
    zones_geojson_path: Path,
    accessibility_rows: list[dict[str, Any]],
    maps_dir: Path,
    *,
    scenario_id: str,
    cutoff_min: int | None = None,
) -> Path:
    folium_module = _require_folium()
    zones_geojson = read_json(zones_geojson_path)

    sums: dict[str, float] = {}
    for row in accessibility_rows:
        if str(row.get("scenario_id")) != scenario_id:
            continue
        if cutoff_min is not None and int(row.get("cutoff_min", 0)) != cutoff_min:
            continue
        zone_id = str(row["origin_zone_id"])
        sums[zone_id] = sums.get(zone_id, 0.0) + float(row.get("jobs_accessible", 0) or 0)

    maps_dir.mkdir(parents=True, exist_ok=True)
    cutoff_suffix = f"_{cutoff_min}min" if cutoff_min else ""
    output = maps_dir / f"access_{scenario_id}{cutoff_suffix}.html"
    caption = (
        f"Jobs accessible — {scenario_id}"
        + (f" ({cutoff_min}-min cutoff)" if cutoff_min else "")
    )
    map_object = _choropleth(folium_module, zones_geojson, sums, caption=caption)
    map_object.save(str(output))
    return output


def zones_vmt_map(
    zones_geojson_path: Path,
    socio_rows: list[dict[str, Any]],
    maps_dir: Path,
    *,
    daily_vmt_per_capita: float,
) -> Path:
    folium_module = _require_folium()
    zones_geojson = read_json(zones_geojson_path)

    vmt_by_zone = {
        str(row["zone_id"]): float(row.get("population", 0) or 0) * daily_vmt_per_capita
        for row in socio_rows
    }

    maps_dir.mkdir(parents=True, exist_ok=True)
    output = maps_dir / "vmt_by_zone.html"
    map_object = _choropleth(
        folium_module,
        zones_geojson,
        vmt_by_zone,
        caption="Screening daily VMT by zone",
        color_scheme="YlOrRd",
    )
    map_object.save(str(output))
    return output


def zones_population_map(
    zones_geojson_path: Path,
    socio_rows: list[dict[str, Any]],
    maps_dir: Path,
) -> Path:
    folium_module = _require_folium()
    zones_geojson = read_json(zones_geojson_path)

    population_by_zone = {
        str(row["zone_id"]): float(row.get("population", 0) or 0)
        for row in socio_rows
    }

    maps_dir.mkdir(parents=True, exist_ok=True)
    output = maps_dir / "population_by_zone.html"
    map_object = _choropleth(
        folium_module,
        zones_geojson,
        population_by_zone,
        caption="Population by zone",
        color_scheme="BuPu",
    )
    map_object.save(str(output))
    return output


def project_score_map(
    projects: list[dict[str, Any]],
    maps_dir: Path,
) -> Path | None:
    geocoded = [
        project
        for project in projects
        if project.get("lat") not in (None, "") and project.get("lon") not in (None, "")
    ]
    if not geocoded:
        return None

    folium_module = _require_folium()
    latitudes = [float(project["lat"]) for project in geocoded]
    longitudes = [float(project["lon"]) for project in geocoded]
    center = [sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes)]

    map_object = folium_module.Map(location=center, zoom_start=11, control_scale=True)
    for project in geocoded:
        label = (
            f"{project.get('name') or project.get('project_id')} "
            f"(score {float(project.get('total_score', 0) or 0):.1f})"
        )
        folium_module.CircleMarker(
            location=[float(project["lat"]), float(project["lon"])],
            radius=6,
            color="#2f855a",
            fill=True,
            fill_opacity=0.8,
            popup=label,
            tooltip=label,
        ).add_to(map_object)

    maps_dir.mkdir(parents=True, exist_ok=True)
    output = maps_dir / "project_scores.html"
    map_object.save(str(output))
    return output


def map_fact_block(
    fact_id: str,
    fact_type: str,
    claim_text: str,
    map_path: Path,
    method_ref: str,
    *,
    scenario_id: str | None = None,
    zones_path: Path | None = None,
) -> dict[str, Any]:
    artifact_refs: list[dict[str, str]] = [
        {"type": "map", "path": str(map_path)},
    ]
    if zones_path is not None:
        artifact_refs.append({"type": "geojson", "path": str(zones_path)})
    return {
        "fact_id": fact_id,
        "fact_type": fact_type,
        "claim_text": claim_text,
        "artifact_refs": artifact_refs,
        "map_ref": str(map_path),
        "scenario_id": scenario_id,
        "method_ref": method_ref,
        "created_at": utc_now(),
    }


def render_standard_maps(
    zones_geojson_path: Path,
    accessibility_rows: list[dict[str, Any]],
    socio_rows: list[dict[str, Any]],
    project_rows: list[dict[str, Any]],
    maps_dir: Path,
    *,
    daily_vmt_per_capita: float,
) -> tuple[list[Path], list[dict[str, Any]]]:
    map_paths: list[Path] = []
    fact_blocks: list[dict[str, Any]] = []

    if socio_rows:
        population_path = zones_population_map(zones_geojson_path, socio_rows, maps_dir)
        map_paths.append(population_path)
        fact_blocks.append(
            map_fact_block(
                "map-population",
                "map_population",
                "Population choropleth across the study-area zones.",
                population_path,
                "map.population_choropleth",
                zones_path=zones_geojson_path,
            )
        )

        vmt_path = zones_vmt_map(
            zones_geojson_path,
            socio_rows,
            maps_dir,
            daily_vmt_per_capita=daily_vmt_per_capita,
        )
        map_paths.append(vmt_path)
        fact_blocks.append(
            map_fact_block(
                "map-vmt",
                "map_vmt",
                "Screening daily VMT choropleth by zone (population × per-capita proxy).",
                vmt_path,
                "map.vmt_proxy_choropleth",
                zones_path=zones_geojson_path,
            )
        )

    if accessibility_rows:
        scenarios = sorted({str(row["scenario_id"]) for row in accessibility_rows})
        for scenario_id in scenarios:
            path = zones_accessibility_map(
                zones_geojson_path,
                accessibility_rows,
                maps_dir,
                scenario_id=scenario_id,
            )
            map_paths.append(path)
            fact_blocks.append(
                map_fact_block(
                    f"map-access-{scenario_id}",
                    "map_accessibility",
                    f"Jobs-accessible choropleth for scenario {scenario_id}.",
                    path,
                    "map.access_choropleth",
                    scenario_id=scenario_id,
                    zones_path=zones_geojson_path,
                )
            )

    project_map = project_score_map(project_rows, maps_dir)
    if project_map is not None:
        map_paths.append(project_map)
        fact_blocks.append(
            map_fact_block(
                "map-project-scores",
                "map_project_scores",
                "Geolocated project markers sized by total score.",
                project_map,
                "map.project_scores",
            )
        )

    return map_paths, fact_blocks


__all__ = [
    "MapDependencyMissingError",
    "map_fact_block",
    "project_score_map",
    "render_standard_maps",
    "zones_accessibility_map",
    "zones_population_map",
    "zones_vmt_map",
]
