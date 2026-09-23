import { useEffect, useRef } from 'react'
import L from 'leaflet'

const PIN_COLORS = { 1: '#22c55e', 2: '#f59e0b', 3: '#ef4444' }

function pinIcon(item) {
  const color = PIN_COLORS[item.price_level] || '#3b82f6'
  return L.divIcon({
    className: 'marker-wrap',
    html: `<div class="marker-pin" style="--pc:${color}">${'$'.repeat(item.price_level || 1)}</div>`,
    iconSize: [34, 40],
    iconAnchor: [17, 38],
    popupAnchor: [0, -34],
  })
}

function hkuIcon() {
  return L.divIcon({
    className: 'marker-wrap',
    html: `<div class="marker-hku">🎓</div>`,
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  })
}

export default function MapView({ items, selectedId, onSelect, center }) {
  const mapEl = useRef(null)
  const mapObj = useRef(null)
  const layerRef = useRef(null)

  useEffect(() => {
    if (!mapEl.current || mapObj.current) return
    mapObj.current = L.map(mapEl.current, { scrollWheelZoom: true }).setView(
      [center?.lat ?? 22.284, center?.lng ?? 114.1355],
      15,
    )
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(mapObj.current)
    const hku = L.marker([center?.lat ?? 22.284, center?.lng ?? 114.1355], {
      icon: hkuIcon(),
      zIndexOffset: 1000,
    })
    hku.addTo(mapObj.current).bindPopup('<b>HKU Main Campus</b>')
    layerRef.current = L.layerGroup().addTo(mapObj.current)
    // give leaflet a moment to size correctly inside flex layout
    setTimeout(() => mapObj.current?.invalidateSize(), 120)
    return () => {
      mapObj.current?.remove()
      mapObj.current = null
    }
  }, [center])

  useEffect(() => {
    if (!mapObj.current || !layerRef.current) return
    layerRef.current.clearLayers()
    const latlngs = []
    items.forEach((item) => {
      const marker = L.marker([item.lat, item.lng], {
        icon: pinIcon(item),
        zIndexOffset: selectedId === item.id ? 100 : 0,
      })
      marker
        .bindPopup(
          `<div class="map-popup">
             <img src="${item.hero_image}" alt="${item.name.replaceAll('"', '')}" />
             <strong>${item.name}</strong><br/>
             <span class="dim">${item.cuisine} · ★ ${item.rating.toFixed(1)} · ${item.walk_minutes} min walk</span>
           </div>`,
        )
        .on('click', () => onSelect(item.id))
      marker.addTo(layerRef.current)
      latlngs.push([item.lat, item.lng])
    })
    if (latlngs.length > 0) {
      mapObj.current.fitBounds(L.latLngBounds(latlngs).pad(0.25), { maxZoom: 16 })
    } else if (center) {
      mapObj.current.setView([center.lat, center.lng], 15)
    }
  }, [items, selectedId, onSelect, center])

  return <div className="map" ref={mapEl} />
}
