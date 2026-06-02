<template>
  <svg
    ref="svgRef"
    class="h-full w-full overflow-visible"
    viewBox="0 0 720 300"
    role="img"
    aria-label="price chart"
    @pointerleave="hoverIndex = null"
  >
    <line
      v-for="tick in yTicks"
      :key="tick.value"
      :x1="plot.left"
      :y1="tick.y"
      :x2="plot.right"
      :y2="tick.y"
      :stroke="tick.index === yTicks.length - 1 ? '#32383e' : '#252a2f'"
      stroke-width="1"
    />
    <line :x1="plot.left" :y1="plot.top" :x2="plot.left" :y2="plot.bottom" stroke="#32383e" stroke-width="1" />
    <line :x1="plot.left" :y1="plot.bottom" :x2="plot.right" :y2="plot.bottom" stroke="#32383e" stroke-width="1" />

    <g v-for="tick in yTicks" :key="`y-${tick.value}`">
      <text :x="plot.left - 10" :y="tick.y + 4" text-anchor="end" fill="#8e99a3" font-size="12">
        {{ formatAxisNumber(tick.value) }}
      </text>
    </g>

    <g v-for="tick in xTicks" :key="`x-${tick.label}`">
      <line :x1="tick.x" :y1="plot.bottom" :x2="tick.x" :y2="plot.bottom + 5" stroke="#32383e" stroke-width="1" />
      <text :x="tick.x" :y="plot.bottom + 24" text-anchor="middle" fill="#8e99a3" font-size="12">
        {{ tick.label }}
      </text>
    </g>

    <g v-if="mode === 'candlestick'">
      <g v-for="candle in candles" :key="candle.point.date">
        <line
          :x1="candle.x"
          :y1="candle.highY"
          :x2="candle.x"
          :y2="candle.lowY"
          :stroke="candle.color"
          stroke-width="1.5"
          stroke-linecap="round"
        />
        <rect
          :x="candle.bodyX"
          :y="candle.bodyY"
          :width="candle.bodyWidth"
          :height="candle.bodyHeight"
          :fill="candle.color"
          :stroke="candle.color"
          rx="1"
        />
      </g>
    </g>
    <path v-else-if="path" :d="path" fill="none" :stroke="stroke" stroke-width="3" stroke-linecap="round" />
    <path
      v-for="average in movingAverageLines"
      :key="average.period"
      :d="average.path"
      fill="none"
      :stroke="average.color"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    />
    <circle v-if="mode === 'line' && lastPoint" :cx="lastPoint.x" :cy="lastPoint.y" r="5" :fill="stroke" />
    <g v-if="hoverEntry">
      <line :x1="hoverEntry.x" :y1="plot.top" :x2="hoverEntry.x" :y2="plot.bottom" stroke="#7dd3fc" stroke-width="1" stroke-dasharray="4 4" />
      <circle :cx="hoverEntry.x" :cy="hoverEntry.y" r="5" fill="#7dd3fc" stroke="#101214" stroke-width="2" />
      <g :transform="`translate(${tooltipX}, ${tooltipY})`">
        <rect width="168" :height="tooltipHeight" rx="4" fill="#171a1d" stroke="#32383e" />
        <text x="10" y="20" fill="#f4f7f8" font-size="12">{{ hoverEntry.point.date }}</text>
        <text x="10" y="39" fill="#7dd3fc" font-size="13" font-weight="600">終値 {{ formatAxisNumber(hoverEntry.point.close ?? 0) }}</text>
        <g v-if="mode === 'candlestick'" fill="#8e99a3" font-size="11">
          <text x="10" y="58">始値 {{ formatNullableAxisNumber(hoverEntry.point.open) }}</text>
          <text x="90" y="58">高値 {{ formatNullableAxisNumber(hoverEntry.point.high) }}</text>
          <text x="10" y="75">安値 {{ formatNullableAxisNumber(hoverEntry.point.low) }}</text>
        </g>
        <g v-if="hoverMovingAverages.length > 0" font-size="11">
          <text
            v-for="(average, index) in hoverMovingAverages"
            :key="average.period"
            x="10"
            :y="movingAverageTooltipStartY + index * 17"
            :fill="average.color"
          >
            {{ average.label }} {{ formatAxisNumber(average.value) }}
          </text>
        </g>
      </g>
    </g>
    <rect
      :x="plot.left"
      :y="plot.top"
      :width="plotWidth"
      :height="plotHeight"
      fill="transparent"
      @pointermove="handlePointerMove"
    />
    <text v-if="!hasVisibleData" x="390" y="144" text-anchor="middle" fill="#8e99a3" font-size="14">データ未取得</text>
  </svg>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PricePoint } from '../lib/api'

const props = defineProps<{
  points: PricePoint[]
  mode?: 'line' | 'candlestick'
  movingAverages?: number[]
}>()

const MOVING_AVERAGE_CONFIG = [
  { period: 5, label: '5日線', color: '#facc15' },
  { period: 25, label: '25日線', color: '#38bdf8' },
  { period: 75, label: '75日線', color: '#c084fc' }
]

const plot = {
  left: 84,
  right: 700,
  top: 18,
  bottom: 252
}
const plotWidth = plot.right - plot.left
const plotHeight = plot.bottom - plot.top
const svgRef = ref<SVGSVGElement | null>(null)
const hoverIndex = ref<number | null>(null)
const mode = computed(() => props.mode ?? 'line')
const activeMovingAverages = computed(() => new Set(props.movingAverages ?? []))

const chartPoints = computed(() => props.points.filter((point) => point.close !== null))
const candlePoints = computed(() =>
  props.points.filter(
    (point) => point.open !== null && point.high !== null && point.low !== null && point.close !== null
  )
)
const visiblePoints = computed(() => (mode.value === 'candlestick' ? candlePoints.value : chartPoints.value))
const stroke = computed(() => {
  const first = visiblePoints.value[0]?.close ?? 0
  const last = visiblePoints.value[visiblePoints.value.length - 1]?.close ?? 0
  return last >= first ? '#48c78e' : '#ff6b6b'
})

const mapped = computed(() => {
  const closes = chartPoints.value.map((point) => point.close as number)
  if (closes.length < 2) return []
  return closes.map((close, index) => ({
    x: plot.left + (index / (closes.length - 1)) * plotWidth,
    y: scaleToY(close)
  }))
})

const movingAverageLines = computed(() =>
  MOVING_AVERAGE_CONFIG.filter((config) => activeMovingAverages.value.has(config.period))
    .map((config) => {
      const points = buildMovingAveragePoints(config.period)
      return {
        ...config,
        points,
        path: pointsToPath(points)
      }
    })
    .filter((average) => average.path)
)

const candles = computed(() => {
  const points = candlePoints.value
  if (points.length < 1) return []
  const step = points.length > 1 ? plotWidth / (points.length - 1) : plotWidth
  const bodyWidth = Math.max(3, Math.min(12, step * 0.58))
  return points.map((point, index) => {
    const open = point.open as number
    const high = point.high as number
    const low = point.low as number
    const close = point.close as number
    const openY = scaleToY(open)
    const closeY = scaleToY(close)
    const bodyHeight = Math.max(2, Math.abs(openY - closeY))
    const x = points.length > 1 ? plot.left + (index / (points.length - 1)) * plotWidth : plot.left + plotWidth / 2
    return {
      x,
      bodyX: x - bodyWidth / 2,
      bodyY: Math.min(openY, closeY) - (bodyHeight === 2 ? 1 : 0),
      bodyWidth,
      bodyHeight,
      highY: scaleToY(high),
      lowY: scaleToY(low),
      color: close >= open ? '#48c78e' : '#ff6b6b',
      point
    }
  })
})

const path = computed(() =>
  mapped.value.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
)
const lastPoint = computed(() => mapped.value[mapped.value.length - 1])
const entries = computed(() =>
  mode.value === 'candlestick'
    ? candles.value.map((candle) => ({
        x: candle.x,
        y: scaleToY(candle.point.close as number),
        point: candle.point
      }))
    : mapped.value.map((mappedPoint, index) => ({
        ...mappedPoint,
        point: chartPoints.value[index]
      }))
)
const hoverEntry = computed(() => (hoverIndex.value === null ? null : entries.value[hoverIndex.value] ?? null))
const hasVisibleData = computed(() => (mode.value === 'candlestick' ? candles.value.length > 0 : Boolean(path.value)))
const hoverMovingAverages = computed(() => {
  if (hoverIndex.value === null) return []
  return movingAverageLines.value.flatMap((average) => {
    const point = average.points.find((entry) => entry.point.date === hoverEntry.value?.point.date)
    return point ? [{ period: average.period, label: average.label, color: average.color, value: point.value }] : []
  })
})
const movingAverageTooltipStartY = computed(() => (mode.value === 'candlestick' ? 92 : 58))
const tooltipHeight = computed(() => {
  const baseHeight = mode.value === 'candlestick' ? 88 : 52
  return baseHeight + hoverMovingAverages.value.length * 17
})
const tooltipX = computed(() => {
  if (!hoverEntry.value) return 0
  return Math.min(Math.max(hoverEntry.value.x + 12, plot.left), plot.right - 168)
})
const tooltipY = computed(() => {
  if (!hoverEntry.value) return 0
  return hoverEntry.value.y > plot.top + tooltipHeight.value + 10
    ? hoverEntry.value.y - tooltipHeight.value - 10
    : hoverEntry.value.y + 12
})

const scale = computed(() => {
  const values =
    mode.value === 'candlestick'
      ? candlePoints.value.flatMap((point) => [point.high as number, point.low as number])
      : chartPoints.value.map((point) => point.close as number)
  const min = values.length ? Math.min(...values) : 0
  const max = values.length ? Math.max(...values) : 0
  const span = max - min || 1
  return { min, max, span }
})

const yTicks = computed(() =>
  Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4
    return {
      index,
      value: scale.value.max - scale.value.span * ratio,
      y: plot.top + plotHeight * ratio
    }
  })
)

const xTicks = computed(() => {
  const points = visiblePoints.value
  if (points.length === 0) return []
  const count = Math.min(5, points.length)
  return Array.from({ length: count }, (_, index) => {
    const pointIndex = count === 1 ? 0 : Math.round((index / (count - 1)) * (points.length - 1))
    const point = points[pointIndex]
    return {
      x: plot.left + (pointIndex / Math.max(points.length - 1, 1)) * plotWidth,
      label: formatDate(point.date)
    }
  })
})

function formatAxisNumber(value: number) {
  return new Intl.NumberFormat('ja-JP', {
    notation: Math.abs(value) >= 100000 ? 'compact' : 'standard',
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2
  }).format(value)
}

function formatNullableAxisNumber(value: number | null) {
  return value === null ? 'N/A' : formatAxisNumber(value)
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric',
    day: 'numeric'
  }).format(date)
}

function scaleToY(value: number) {
  return plot.bottom - ((value - scale.value.min) / scale.value.span) * plotHeight
}

function buildMovingAveragePoints(period: number) {
  const points = chartPoints.value
  if (points.length < period) return []
  return points.flatMap((point, index) => {
    if (index < period - 1) return []
    const slice = points.slice(index - period + 1, index + 1)
    const value = slice.reduce((sum, entry) => sum + (entry.close as number), 0) / period
    return [
      {
        x: plot.left + (index / Math.max(points.length - 1, 1)) * plotWidth,
        y: scaleToY(value),
        value,
        point
      }
    ]
  })
}

function pointsToPath(points: { x: number; y: number }[]) {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
}

function handlePointerMove(event: PointerEvent) {
  if (!svgRef.value || entries.value.length === 0) return
  const point = svgRef.value.createSVGPoint()
  point.x = event.clientX
  point.y = event.clientY
  const matrix = svgRef.value.getScreenCTM()
  if (!matrix) return
  const cursor = point.matrixTransform(matrix.inverse())
  let nearestIndex = 0
  let nearestDistance = Number.POSITIVE_INFINITY
  entries.value.forEach((entry, index) => {
    const distance = Math.abs(entry.x - cursor.x)
    if (distance < nearestDistance) {
      nearestDistance = distance
      nearestIndex = index
    }
  })
  hoverIndex.value = nearestIndex
}
</script>
