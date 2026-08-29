import { useEffect, useState } from 'react'

interface Props {
  features: Record<string, number>
}

/** 六维特征雷达图（AIGC 检测维度可视化） */
export default function Radar({ features }: Props) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 30)
    return () => clearTimeout(t)
  }, [])

  const entries = Object.entries(features).slice(0, 8)
  const n = entries.length
  if (n < 3) return null

  const size = 260
  const cx = size / 2
  const cy = size / 2 + 6
  const R = 88
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2

  const rings = [0.25, 0.5, 0.75, 1].map(f => (
    <circle key={f} cx={cx} cy={cy} r={R * f} fill="none" stroke="#e2e8f0" strokeWidth={1} />
  ))

  const spokes = entries.map((_, i) => {
    const x = cx + R * Math.cos(angle(i))
    const y = cy + R * Math.sin(angle(i))
    return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="#e2e8f0" strokeWidth={1} />
  })

  const polygon = entries
    .map(([_, v], i) => {
      const f = (mounted ? v : 0) / 100
      const x = cx + R * f * Math.cos(angle(i))
      const y = cy + R * f * Math.sin(angle(i))
      return `${x},${y}`
    })
    .join(' ')

  const points = entries
    .map(([_, v], i) => {
      const f = (mounted ? v : 0) / 100
      return {
        x: cx + R * f * Math.cos(angle(i)),
        y: cy + R * f * Math.sin(angle(i)),
      }
    })

  const labels = entries.map(([name, v], i) => {
    const lx = cx + (R + 26) * Math.cos(angle(i))
    const ly = cy + (R + 26) * Math.sin(angle(i))
    return (
      <text
        key={name}
        x={lx}
        y={ly}
        textAnchor="middle"
        dominantBaseline="middle"
        fontSize={11}
        fill="#475569"
      >
        {name} {v}
      </text>
    )
  })

  return (
    <svg width={size} height={size + 10} className="mx-auto">
      {rings}
      {spokes}
      <polygon points={polygon} fill="rgba(139,92,246,0.25)" stroke="#8b5cf6" strokeWidth={2} />
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r={3.5} fill="#8b5cf6" />
      ))}
      {labels}
    </svg>
  )
}
