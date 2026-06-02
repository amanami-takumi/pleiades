<template>
  <div class="min-h-screen bg-background text-neutral-100">
    <aside class="fixed left-0 top-0 z-20 hidden h-screen w-20 border-r border-border bg-panel lg:flex lg:flex-col lg:items-center lg:py-5">
      <div class="mb-8 flex h-11 w-11 items-center justify-center rounded-md bg-panel2 text-accent">
        <Layers :size="24" />
      </div>
      <nav class="flex flex-1 flex-col gap-2">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          :title="tab.label"
          class="flex h-12 w-12 items-center justify-center rounded-md border transition"
          :class="activeTab === tab.key ? 'border-accent bg-accent/15 text-accent' : 'border-transparent text-neutral-400 hover:border-border hover:text-neutral-100'"
          @click="activeTab = tab.key"
        >
          <component :is="tab.icon" :size="21" />
        </button>
      </nav>
    </aside>

    <main class="min-h-screen lg:pl-20">
      <section v-if="activeTab === 'invest'" class="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header class="flex flex-col gap-4 border-b border-border pb-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p class="text-sm font-medium text-accent">Pleiades</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-normal text-neutral-50 sm:text-3xl">投資情報</h1>
            <p class="mt-2 text-sm text-neutral-400">yfinance から取得した指数・銘柄を SQLite に保存して表示します。</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <form class="flex min-w-0 flex-1 gap-2 sm:flex-none" @submit.prevent="addSymbol">
              <input
                v-model="newTicker"
                class="h-10 w-36 rounded-md border border-border bg-panel px-3 text-sm outline-none transition placeholder:text-neutral-600 focus:border-accent"
                placeholder="AAPL"
              />
              <select v-model="newAssetType" class="h-10 rounded-md border border-border bg-panel px-3 text-sm outline-none focus:border-accent">
                <option value="stock">株式</option>
                <option value="fund">投信</option>
                <option value="index">指数</option>
              </select>
              <button class="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-sky-300" type="submit">
                <Plus :size="17" />追加
              </button>
            </form>
            <button class="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium text-neutral-100 transition hover:border-accent" type="button" @click="refresh">
              <RefreshCw :size="17" :class="{ 'animate-spin': refreshing }" />全更新
            </button>
          </div>
        </header>

        <p v-if="error" class="rounded-md border border-loss/40 bg-loss/10 px-3 py-2 text-sm text-red-200">{{ error }}</p>

        <div class="grid gap-5 xl:grid-cols-[minmax(280px,380px)_minmax(0,1fr)]">
          <section class="min-h-[420px] overflow-hidden rounded-md border border-border bg-panel">
            <div class="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 class="text-sm font-semibold text-neutral-200">ウォッチリスト</h2>
              <span class="text-xs text-neutral-500">{{ symbols.length }}件</span>
            </div>
            <div class="flex gap-1 overflow-x-auto border-b border-border px-3 py-2">
              <button
                v-for="tag in symbolTags"
                :key="tag"
                type="button"
                class="h-8 shrink-0 rounded px-3 text-xs font-medium transition"
                :class="activeSymbolTag === tag ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                @click="activeSymbolTag = tag"
              >
                {{ tag }}
              </button>
            </div>
            <div class="max-h-[calc(100vh-220px)] overflow-auto">
              <button
                v-for="symbol in visibleSymbols"
                :key="symbol.id"
                type="button"
                draggable="true"
                class="grid w-full grid-cols-[auto_1fr_auto] gap-2 border-b border-border/70 px-3 py-3 text-left transition hover:bg-panel2"
                :class="[
                  selectedId === symbol.id ? 'bg-panel2' : '',
                  draggingSymbolId === symbol.id ? 'opacity-50' : ''
                ]"
                @click="selectSymbol(symbol.id)"
                @dragstart="startSymbolDrag(symbol.id)"
                @dragover.prevent
                @drop="dropSymbol(symbol.id)"
                @dragend="endSymbolDrag"
              >
                <span class="flex h-9 w-5 items-center justify-center text-neutral-600">
                  <GripVertical :size="15" />
                </span>
                <span class="min-w-0">
                  <span class="block truncate text-sm font-semibold text-neutral-100">{{ symbol.ticker }}</span>
                  <span class="block truncate text-xs" :class="symbol.last_error ? 'text-loss' : 'text-neutral-500'">{{ symbol.last_error ? '取得エラー' : symbol.name }}</span>
                  <span class="mt-1 inline-flex max-w-full items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-neutral-500" :title="symbol.tag">
                    <Tag :size="11" class="shrink-0" />
                    <span class="truncate">{{ symbol.tag }}</span>
                  </span>
                </span>
                <span class="text-right">
                  <span class="block text-sm font-medium">{{ money(symbol.latest_close, symbol.currency) }}</span>
                  <span class="flex items-center justify-end gap-1 text-xs" :class="symbol.last_error ? 'text-loss' : percentClass(symbol.change_1d_percent)">
                    <AlertTriangle v-if="symbol.last_error" :size="13" />
                    {{ symbol.last_error ? 'Error' : percent(symbol.change_1d_percent) }}
                  </span>
                </span>
              </button>
            </div>
          </section>

          <section class="min-w-0 rounded-md border border-border bg-panel">
            <div v-if="selectedSymbol" class="flex h-full flex-col">
              <div class="flex flex-col gap-3 border-b border-border px-4 py-4 md:flex-row md:items-center md:justify-between">
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <h2 class="truncate text-xl font-semibold text-neutral-50">{{ selectedSymbol.ticker }}</h2>
                    <span class="rounded border border-border px-2 py-0.5 text-xs text-neutral-400">{{ selectedSymbol.asset_type }}</span>
                  </div>
                  <p class="mt-1 truncate text-sm text-neutral-400">{{ selectedSymbol.name }} / {{ selectedSymbol.exchange ?? 'N/A' }}</p>
                  <form class="mt-3 flex max-w-sm items-center gap-2" @submit.prevent="saveSelectedTag">
                    <Tag :size="15" class="shrink-0 text-neutral-500" />
                    <input
                      v-model="tagDraft"
                      class="h-8 min-w-0 flex-1 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent"
                      placeholder="タグ"
                    />
                    <button class="h-8 rounded-md border border-border px-3 text-xs font-medium text-neutral-200 hover:border-accent" type="submit">保存</button>
                  </form>
                </div>
                <div class="flex flex-wrap items-center justify-end gap-2">
                  <div class="flex rounded-md border border-border bg-background p-1">
                    <button
                      v-for="mode in chartModes"
                      :key="mode.value"
                      type="button"
                      class="inline-flex h-8 items-center gap-1.5 rounded px-2.5 text-xs font-medium transition"
                      :class="chartMode === mode.value ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                      :title="mode.label"
                      @click="chartMode = mode.value"
                    >
                      <component :is="mode.icon" :size="14" />
                      {{ mode.label }}
                    </button>
                  </div>
                  <div class="flex rounded-md border border-border bg-background p-1">
                    <button
                      v-for="average in movingAverageOptions"
                      :key="average.period"
                      type="button"
                      class="h-8 rounded px-2.5 text-xs font-medium transition"
                      :class="movingAveragePeriods.includes(average.period) ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                      :title="average.label"
                      @click="toggleMovingAverage(average.period)"
                    >
                      {{ average.shortLabel }}
                    </button>
                  </div>
                  <div class="flex rounded-md border border-border bg-background p-1">
                    <button
                      v-for="range in ranges"
                      :key="range.value"
                      type="button"
                      class="h-8 rounded px-3 text-xs font-medium transition"
                      :class="activeRange === range.value ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                      @click="setRange(range.value)"
                    >
                      {{ range.label }}
                    </button>
                  </div>
                  <button class="flex h-10 w-10 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-loss hover:text-loss" type="button" title="削除" @click="removeSelected">
                    <Trash2 :size="17" />
                  </button>
                  <button class="flex h-10 w-10 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-accent hover:text-accent" type="button" title="この銘柄を更新" @click="refreshSelected">
                    <RefreshCw :size="17" :class="{ 'animate-spin': selectedRefreshing }" />
                  </button>
                </div>
              </div>

              <div class="grid gap-3 border-b border-border p-4 sm:grid-cols-2 xl:grid-cols-4">
                <Metric label="現在値" :value="money(selectedSymbol.latest_close, selectedSymbol.currency)" />
                <Metric label="騰落率" :value="percent(totalReturn)" :tone="totalReturn ?? undefined" />
                <Metric label="PER" :value="number(selectedSymbol.per)" />
                <Metric label="PBR / ROE" :value="`${number(selectedSymbol.pbr)} / ${selectedSymbol.roe === null ? 'N/A' : percent(selectedSymbol.roe * 100)}`" />
              </div>

              <div v-if="selectedSymbol.last_error" class="mx-4 mt-4 rounded-md border border-loss/40 bg-loss/10 px-3 py-3 text-sm text-red-100">
                <div class="flex items-center gap-2 font-semibold text-red-200">
                  <AlertTriangle :size="16" />取得エラー
                </div>
                <p class="mt-2 break-words text-red-100">{{ selectedSymbol.last_error }}</p>
                <p class="mt-1 text-xs text-red-200/70">最終試行: {{ selectedSymbol.last_refreshed_at ?? 'N/A' }}</p>
              </div>

              <div class="h-[320px] p-4">
                <SparklineChart :points="history" :mode="chartMode" :moving-averages="movingAveragePeriods" />
              </div>

              <div class="grid gap-3 px-4 pb-4 sm:grid-cols-3">
                <Metric label="時価総額" :value="compact(selectedSymbol.market_cap)" />
                <Metric label="配当利回り" :value="percent(selectedSymbol.dividend_yield)" />
                <Metric label="最終更新日時" :value="formatDateTime(selectedSymbol.last_refreshed_at)" />
              </div>

              <section class="border-t border-border px-4 py-4">
                <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <h3 class="text-sm font-semibold text-neutral-200">保有・収支</h3>
                  <form class="grid gap-2 sm:grid-cols-[130px_120px_100px_minmax(120px,1fr)_auto]" @submit.prevent="addPurchase">
                    <input v-model="purchaseDate" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" type="date" />
                    <input v-model.number="purchaseAmount" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" min="0" step="0.01" type="number" :placeholder="purchaseAmountPlaceholder" />
                    <input v-model.number="purchaseQuantity" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" min="0" step="0.0001" type="number" placeholder="数量" />
                    <input v-model="purchaseNote" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" placeholder="メモ" />
                    <button class="inline-flex h-9 items-center gap-1 rounded-md bg-accent px-3 text-xs font-semibold text-neutral-950 hover:bg-sky-300" type="submit">
                      <Plus :size="14" />追加
                    </button>
                  </form>
                </div>

                <div class="grid gap-3 sm:grid-cols-4">
                  <Metric label="投資額" :value="moneyValue(position.totalCost, selectedSymbol.currency)" />
                  <Metric label="保有数量" :value="number(position.totalQuantity)" />
                  <Metric label="評価額" :value="moneyValue(position.marketValue, selectedSymbol.currency)" />
                  <Metric label="評価損益" :value="moneyValue(position.profitLoss, selectedSymbol.currency)" :tone="position.profitLoss" />
                </div>

                <div class="mt-3 overflow-x-auto rounded-md border border-border">
                  <table class="w-full min-w-[620px] text-left text-xs">
                    <thead class="border-b border-border text-neutral-500">
                      <tr>
                        <th class="px-3 py-2 font-medium">日付</th>
                        <th class="px-3 py-2 font-medium">購入額</th>
                        <th class="px-3 py-2 font-medium">数量</th>
                        <th class="px-3 py-2 font-medium">単価</th>
                        <th class="px-3 py-2 font-medium">メモ</th>
                        <th class="px-3 py-2 font-medium"></th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="purchase in purchases" :key="purchase.id" class="border-b border-border/70">
                        <td class="px-3 py-2 text-neutral-300">{{ purchase.purchased_at }}</td>
                        <td class="px-3 py-2">{{ moneyValue(purchase.amount, selectedSymbol.currency) }}</td>
                        <td class="px-3 py-2">{{ number(purchase.quantity) }}</td>
                        <td class="px-3 py-2">{{ moneyValue(purchase.unit_price, selectedSymbol.currency) }}</td>
                        <td class="max-w-[180px] truncate px-3 py-2 text-neutral-400" :title="purchase.note ?? ''">{{ purchase.note ?? '' }}</td>
                        <td class="px-3 py-2 text-right">
                          <button class="inline-flex h-7 items-center rounded-md border border-loss/50 px-2 text-loss hover:bg-loss/10" type="button" @click="removePurchase(purchase.id)">
                            <Trash2 :size="13" />
                          </button>
                        </td>
                      </tr>
                      <tr v-if="purchases.length === 0">
                        <td colspan="6" class="px-3 py-5 text-center text-neutral-500">購入履歴はありません</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </section>
            </div>
            <div v-else class="flex h-80 items-center justify-center text-sm text-neutral-500">読み込み中です</div>
          </section>
        </div>

        <section class="rounded-md border border-border bg-panel">
          <div class="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 class="text-sm font-semibold text-neutral-200">更新キュー</h2>
              <p class="mt-1 text-xs text-neutral-500">{{ queueOpen ? '直近50件の更新ジョブ' : `${jobs.length}件のジョブを収納中` }}</p>
            </div>
            <div class="flex items-center gap-2">
              <button class="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-xs font-medium text-neutral-200 hover:border-accent" type="button" @click="queueOpen = !queueOpen">
                <ChevronUp v-if="queueOpen" :size="15" />
                <ChevronDown v-else :size="15" />
                {{ queueOpen ? '収納' : '展開' }}
              </button>
              <button class="inline-flex h-9 items-center gap-2 rounded-md border border-border bg-background px-3 text-xs font-medium text-neutral-200 hover:border-accent" type="button" @click="loadJobs">
                <RefreshCw :size="15" />再読込
              </button>
            </div>
          </div>
          <div v-if="queueOpen" class="overflow-x-auto">
            <table class="w-full min-w-[720px] text-left text-sm">
              <thead class="border-b border-border text-xs text-neutral-500">
                <tr>
                  <th class="px-4 py-2 font-medium">ID</th>
                  <th class="px-4 py-2 font-medium">銘柄</th>
                  <th class="px-4 py-2 font-medium">状態</th>
                  <th class="px-4 py-2 font-medium">投入</th>
                  <th class="px-4 py-2 font-medium">開始</th>
                  <th class="px-4 py-2 font-medium">終了</th>
                  <th class="px-4 py-2 font-medium">エラー</th>
                  <th class="px-4 py-2 font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="job in jobs" :key="job.id" class="border-b border-border/70">
                  <td class="px-4 py-2 text-neutral-400">{{ job.id }}</td>
                  <td class="px-4 py-2 font-medium text-neutral-100">{{ job.ticker }}</td>
                  <td class="px-4 py-2">
                    <span class="rounded border px-2 py-0.5 text-xs" :class="jobStatusClass(job.status)">{{ jobStatusLabel(job.status) }}</span>
                  </td>
                  <td class="px-4 py-2 text-xs text-neutral-400">{{ formatTime(job.queued_at) }}</td>
                  <td class="px-4 py-2 text-xs text-neutral-400">{{ formatTime(job.started_at) }}</td>
                  <td class="px-4 py-2 text-xs text-neutral-400">{{ formatTime(job.finished_at) }}</td>
                  <td class="max-w-[320px] truncate px-4 py-2 text-xs text-loss" :title="job.error ?? ''">{{ job.error ?? '' }}</td>
                  <td class="px-4 py-2">
                    <button
                      v-if="canCancelJob(job)"
                      class="inline-flex h-8 items-center gap-1 rounded-md border border-loss/50 px-2 text-xs font-medium text-loss hover:bg-loss/10"
                      type="button"
                      @click="cancelJob(job.id)"
                    >
                      <X :size="14" />中止
                    </button>
                  </td>
                </tr>
                <tr v-if="jobs.length === 0">
                  <td colspan="8" class="px-4 py-6 text-center text-sm text-neutral-500">キューは空です</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </section>

      <section v-else class="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-6">
        <div class="w-full rounded-md border border-border bg-panel p-6">
          <component :is="currentTab?.icon" class="mb-4 text-accent" :size="28" />
          <h1 class="text-xl font-semibold">{{ currentTab?.label }}</h1>
          <p class="mt-2 text-sm text-neutral-400">この機能は後日実装予定です。</p>
        </div>
      </section>
    </main>

    <div class="fixed bottom-4 right-4 z-30 lg:hidden">
      <button class="flex h-12 w-12 items-center justify-center rounded-md border border-border bg-panel2 p-3 text-neutral-100 shadow-xl" type="button" @click="mobileOpen = !mobileOpen">
        <Menu :size="24" />
      </button>
      <div v-if="mobileOpen" class="absolute bottom-16 right-0 w-56 overflow-hidden rounded-md border border-border bg-panel shadow-2xl">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          type="button"
          class="flex w-full items-center gap-3 px-4 py-3 text-left text-sm hover:bg-panel2"
          :class="activeTab === tab.key ? 'text-accent' : 'text-neutral-200'"
          @click="activeTab = tab.key; mobileOpen = false"
        >
          <component :is="tab.icon" :size="18" />{{ tab.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  BriefcaseBusiness,
  ChartCandlestick,
  ChartLine,
  ChevronDown,
  ChevronUp,
  GripVertical,
  Home,
  Layers,
  Menu,
  Plus,
  RefreshCw,
  Tag,
  Trash2,
  X
} from '@lucide/vue'
import SparklineChart from './components/SparklineChart.vue'
import {
  createSymbol,
  cancelRefreshJob,
  createPurchase,
  deleteSymbol,
  deletePurchase,
  getHistory,
  listRefreshJobs,
  listPurchases,
  listSymbols,
  reorderSymbols,
  refreshAll,
  refreshSymbol,
  updateSymbol,
  type PricePoint,
  type Purchase,
  type RefreshJob,
  type SymbolRow
} from './lib/api'

const Metric = defineComponent({
  props: {
    label: { type: String, required: true },
    value: { type: String, required: true },
    tone: { type: Number, required: false, default: null }
  },
  setup(props) {
    return () =>
      h('div', { class: 'rounded-md border border-border bg-background px-3 py-3' }, [
        h('div', { class: 'text-xs text-neutral-500' }, props.label),
        h(
          'div',
          {
            class: [
              'mt-1 truncate text-lg font-semibold',
              props.tone === null ? 'text-neutral-100' : props.tone >= 0 ? 'text-gain' : 'text-loss'
            ]
          },
          props.value
        )
      ])
  }
})

const tabs = [
  { key: 'invest', label: '投資情報', icon: BriefcaseBusiness },
  { key: 'tasks', label: 'タスク管理', icon: Layers },
  { key: 'home', label: 'スマートホーム', icon: Home }
]
const ranges = [
  { value: '1w', label: '週' },
  { value: '1m', label: '月' },
  { value: '1y', label: '年' },
  { value: '3y', label: '3年' },
  { value: '5y', label: '5年' }
]
const chartModes = [
  { value: 'line' as const, label: 'ライン', icon: ChartLine },
  { value: 'candlestick' as const, label: '日線', icon: ChartCandlestick }
]
const movingAverageOptions = [
  { period: 5, label: '5日移動平均線', shortLabel: '5日' },
  { period: 25, label: '25日移動平均線', shortLabel: '25日' },
  { period: 75, label: '75日移動平均線', shortLabel: '75日' }
]

const activeTab = ref('invest')
const mobileOpen = ref(false)
const symbols = ref<SymbolRow[]>([])
const selectedId = ref<number | null>(null)
const history = ref<PricePoint[]>([])
const activeRange = ref('1y')
const chartMode = ref<(typeof chartModes)[number]['value']>('line')
const movingAveragePeriods = ref<number[]>([])
const newTicker = ref('')
const newAssetType = ref('stock')
const refreshing = ref(false)
const selectedRefreshing = ref(false)
const error = ref('')
const jobs = ref<RefreshJob[]>([])
const queueOpen = ref(false)
const purchases = ref<Purchase[]>([])
const purchaseDate = ref(new Date().toISOString().slice(0, 10))
const purchaseAmount = ref<number | null>(null)
const purchaseQuantity = ref<number | null>(null)
const purchaseNote = ref('')
const activeSymbolTag = ref('すべて')
const tagDraft = ref('')
const draggingSymbolId = ref<number | null>(null)
let jobsTimer: number | undefined

const selectedSymbol = computed(() => symbols.value.find((symbol) => symbol.id === selectedId.value) ?? null)
const currentTab = computed(() => tabs.find((tab) => tab.key === activeTab.value))
const symbolTags = computed(() => {
  const tags = Array.from(new Set(symbols.value.map((symbol) => symbol.tag || 'ウォッチリスト'))).sort((a, b) =>
    a.localeCompare(b, 'ja')
  )
  return ['すべて', ...tags]
})
const visibleSymbols = computed(() =>
  activeSymbolTag.value === 'すべて' ? symbols.value : symbols.value.filter((symbol) => symbol.tag === activeSymbolTag.value)
)
const totalReturn = computed(() => history.value[history.value.length - 1]?.return_percent ?? null)
const isStockPurchaseInput = computed(() => selectedSymbol.value?.asset_type === 'stock')
const purchaseAmountPlaceholder = computed(() => (isStockPurchaseInput.value ? '一株価格' : '購入額'))
const position = computed(() => {
  const totalCost = purchases.value.reduce((sum, purchase) => sum + purchase.amount, 0)
  const totalQuantity = purchases.value.reduce((sum, purchase) => sum + purchase.quantity, 0)
  const marketValue = totalQuantity * (selectedSymbol.value?.latest_close ?? 0)
  return {
    totalCost,
    totalQuantity,
    marketValue,
    profitLoss: marketValue - totalCost
  }
})

watch(selectedSymbol, (symbol) => {
  tagDraft.value = symbol?.tag ?? ''
})

onMounted(async () => {
  await load()
  await loadJobs()
  jobsTimer = window.setInterval(loadJobs, 5000)
})

onUnmounted(() => {
  if (jobsTimer) window.clearInterval(jobsTimer)
})

async function load() {
  try {
    error.value = ''
    symbols.value = await listSymbols()
    selectedId.value = selectedId.value ?? symbols.value[0]?.id ?? null
    if (!symbolTags.value.includes(activeSymbolTag.value)) {
      activeSymbolTag.value = 'すべて'
    }
    await loadHistory()
    await loadPurchases()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '読み込みに失敗しました'
  }
}

async function loadHistory() {
  if (!selectedId.value) return
  const response = await getHistory(selectedId.value, activeRange.value)
  history.value = response.points
}

async function loadPurchases() {
  if (!selectedId.value) {
    purchases.value = []
    return
  }
  purchases.value = await listPurchases(selectedId.value)
}

async function selectSymbol(id: number) {
  selectedId.value = id
  await loadHistory()
  await loadPurchases()
}

async function setRange(range: string) {
  activeRange.value = range
  await loadHistory()
}

function toggleMovingAverage(period: number) {
  movingAveragePeriods.value = movingAveragePeriods.value.includes(period)
    ? movingAveragePeriods.value.filter((value) => value !== period)
    : [...movingAveragePeriods.value, period]
}

async function addSymbol() {
  const ticker = newTicker.value.trim()
  if (!ticker) return
  try {
    error.value = ''
    const tag = activeSymbolTag.value === 'すべて' ? undefined : activeSymbolTag.value
    const created = await createSymbol(ticker, undefined, newAssetType.value, tag)
    newTicker.value = ''
    await load()
    await loadJobs()
    selectedId.value = created.id
    await loadHistory()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '銘柄追加に失敗しました'
  }
}

async function saveSelectedTag() {
  if (!selectedSymbol.value) return
  const tag = tagDraft.value.trim() || 'ウォッチリスト'
  try {
    error.value = ''
    const updated = await updateSymbol(selectedSymbol.value.id, { tag })
    activeSymbolTag.value = updated.tag
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'タグ保存に失敗しました'
  }
}

function startSymbolDrag(id: number) {
  draggingSymbolId.value = id
}

function endSymbolDrag() {
  draggingSymbolId.value = null
}

async function dropSymbol(targetId: number) {
  if (!draggingSymbolId.value || draggingSymbolId.value === targetId) {
    endSymbolDrag()
    return
  }
  const orderedVisible = [...visibleSymbols.value]
  const fromIndex = orderedVisible.findIndex((symbol) => symbol.id === draggingSymbolId.value)
  const toIndex = orderedVisible.findIndex((symbol) => symbol.id === targetId)
  if (fromIndex < 0 || toIndex < 0) {
    endSymbolDrag()
    return
  }
  const [moved] = orderedVisible.splice(fromIndex, 1)
  orderedVisible.splice(toIndex, 0, moved)
  const orderedIds = orderedVisible.map((symbol) => symbol.id)
  const visibleIds = new Set(orderedIds)
  symbols.value = [...orderedVisible, ...symbols.value.filter((symbol) => !visibleIds.has(symbol.id))]
  endSymbolDrag()
  try {
    error.value = ''
    symbols.value = await reorderSymbols(orderedIds)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '並び順の保存に失敗しました'
    await load()
  }
}

async function refresh() {
  refreshing.value = true
  try {
    error.value = ''
    const result = await refreshAll()
    await loadJobs()
    error.value = `${result.queued}件の更新をキューに追加しました`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '更新に失敗しました'
  } finally {
    refreshing.value = false
  }
}

async function refreshSelected() {
  if (!selectedSymbol.value) return
  selectedRefreshing.value = true
  try {
    error.value = ''
    const result = await refreshSymbol(selectedSymbol.value.id)
    await loadJobs()
    error.value = `${selectedSymbol.value.ticker} の更新をキューに追加しました (${result.queued}件)`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '銘柄更新に失敗しました'
  } finally {
    selectedRefreshing.value = false
  }
}

async function loadJobs() {
  try {
    jobs.value = await listRefreshJobs()
    if (jobs.value.some((job) => job.status === 'running' || job.status === 'queued')) {
      await load()
      await loadHistory()
    }
  } catch (err) {
    console.error('Failed to load refresh jobs', err)
  }
}

async function cancelJob(jobId: number) {
  try {
    error.value = ''
    const job = await cancelRefreshJob(jobId)
    await loadJobs()
    error.value = `${job.ticker} のジョブ ${job.id} を中止しました`
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'ジョブ中止に失敗しました'
  }
}

async function addPurchase() {
  if (!selectedSymbol.value || !purchaseAmount.value || !purchaseQuantity.value) return
  try {
    error.value = ''
    const amount = isStockPurchaseInput.value ? purchaseAmount.value * purchaseQuantity.value : purchaseAmount.value
    await createPurchase(selectedSymbol.value.id, {
      purchased_at: purchaseDate.value,
      amount,
      quantity: purchaseQuantity.value,
      note: purchaseNote.value || undefined
    })
    purchaseAmount.value = null
    purchaseQuantity.value = null
    purchaseNote.value = ''
    await loadPurchases()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '購入履歴の追加に失敗しました'
  }
}

async function removePurchase(id: number) {
  try {
    error.value = ''
    await deletePurchase(id)
    await loadPurchases()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '購入履歴の削除に失敗しました'
  }
}

async function removeSelected() {
  if (!selectedSymbol.value || !window.confirm(`${selectedSymbol.value.ticker} を削除しますか？`)) return
  await deleteSymbol(selectedSymbol.value.id)
  selectedId.value = null
  await load()
}

function money(value: number | null, currency: string | null) {
  if (value === null) return 'N/A'
  return new Intl.NumberFormat('ja-JP', {
    style: currency ? 'currency' : 'decimal',
    currency: currency ?? 'JPY',
    maximumFractionDigits: value >= 1000 ? 0 : 2
  }).format(value)
}

function moneyValue(value: number, currency: string | null) {
  return new Intl.NumberFormat('ja-JP', {
    style: currency ? 'currency' : 'decimal',
    currency: currency ?? 'JPY',
    maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2
  }).format(value)
}

function percent(value: number | null) {
  if (value === null || Number.isNaN(value)) return 'N/A'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function percentClass(value: number | null) {
  if (value === null) return 'text-neutral-500'
  return value >= 0 ? 'text-gain' : 'text-loss'
}

function number(value: number | null) {
  if (value === null || Number.isNaN(value)) return 'N/A'
  return new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 2 }).format(value)
}

function compact(value: number | null) {
  if (value === null) return 'N/A'
  return new Intl.NumberFormat('ja-JP', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

function jobStatusLabel(status: string) {
  const labels: Record<string, string> = {
    queued: '待機',
    running: '実行中',
    succeeded: '成功',
    failed: '失敗',
    cancelled: '中止'
  }
  return labels[status] ?? status
}

function jobStatusClass(status: string) {
  if (status === 'succeeded') return 'border-gain/40 bg-gain/10 text-gain'
  if (status === 'failed') return 'border-loss/40 bg-loss/10 text-loss'
  if (status === 'running') return 'border-accent/40 bg-accent/10 text-accent'
  if (status === 'cancelled') return 'border-neutral-600 bg-neutral-800 text-neutral-300'
  return 'border-border bg-background text-neutral-400'
}

function canCancelJob(job: RefreshJob) {
  return !job.cancel_requested && (job.status === 'queued' || job.status === 'running')
}

function formatTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ja-JP', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function formatDateTime(value: string | null) {
  if (!value) return 'N/A'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}
</script>
