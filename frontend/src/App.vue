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
            <p class="mt-2 text-sm text-neutral-400">Yahoo Finance から取得した指数・銘柄を SQLite に保存して表示します。</p>
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
                  <span class="block truncate text-sm font-semibold text-neutral-100">{{ symbol.name }}</span>
                  <span class="block truncate text-xs" :class="symbol.last_error ? 'text-loss' : 'text-neutral-500'">{{ symbol.last_error ? '取得エラー' : symbol.ticker }}</span>
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

          <div class="grid min-w-0 gap-5">
          <section class="min-w-0 rounded-md border border-border bg-panel">
            <div v-if="selectedSymbol" class="flex h-full flex-col">
              <div class="flex flex-col gap-3 px-4 py-4 md:flex-row md:items-start md:justify-between">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2">
                    <h2 class="truncate text-xl font-semibold text-neutral-50">{{ selectedSymbol.name }}</h2>
                    <span class="rounded border border-border px-2 py-0.5 text-xs text-neutral-400">{{ selectedSymbol.asset_type }}</span>
                  </div>
                  <p class="mt-1 truncate text-sm text-neutral-400">{{ selectedSymbol.ticker }} / {{ selectedSymbol.exchange ?? 'N/A' }}</p>
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
                  <button class="flex h-10 w-10 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-loss hover:text-loss" type="button" title="削除" @click="removeSelected">
                    <Trash2 :size="17" />
                  </button>
                  <button class="flex h-10 w-10 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-accent hover:text-accent" type="button" title="この銘柄を更新" @click="refreshSelected">
                    <RefreshCw :size="17" :class="{ 'animate-spin': selectedRefreshing }" />
                  </button>
                </div>
              </div>

              <div class="grid gap-3 border-b border-border px-4 pb-4 sm:grid-cols-2 xl:grid-cols-4">
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
                <p class="mt-1 text-xs text-red-200/70">最終試行: {{ formatDateTime(selectedSymbol.last_refreshed_at) }}</p>
              </div>

              <div class="flex flex-wrap items-center gap-2 border-b border-border p-4">
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
                    v-for="drawing in chartDrawingModes"
                    :key="drawing.value"
                    type="button"
                    class="h-8 rounded px-2.5 text-xs font-medium transition"
                    :class="chartDrawingMode === drawing.value ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                    :title="drawing.label"
                    @click="chartDrawingMode = drawing.value"
                  >
                    {{ drawing.shortLabel }}
                  </button>
                </div>
                <button
                  class="inline-flex h-10 items-center gap-1 rounded-md border border-border px-2.5 text-xs font-medium text-neutral-400 hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  title="サポート/レジスタンスラインを削除"
                  :disabled="selectedChartGuideLines.length === 0"
                  @click="clearSelectedChartGuideLines"
                >
                  <X :size="14" />ライン
                </button>
              </div>

              <div class="h-[320px] p-4">
                <SparklineChart
                  :points="history"
                  :mode="chartMode"
                  :moving-averages="movingAveragePeriods"
                  :drawing-mode="chartDrawingMode"
                  :guide-lines="selectedChartGuideLines"
                  @update:guide-lines="setSelectedChartGuideLines"
                />
              </div>

              <div class="grid gap-3 px-4 pb-4 sm:grid-cols-3">
                <Metric label="時価総額" :value="compact(selectedSymbol.market_cap)" />
                <Metric label="配当利回り" :value="percent(selectedSymbol.dividend_yield)" />
                <Metric label="最終更新日時" :value="formatDateTime(selectedSymbol.last_refreshed_at)" />
              </div>

              <section class="border-t border-border px-4 py-4">
                <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <h3 class="text-sm font-semibold text-neutral-200">保有・収支</h3>
                  <form
                    class="grid gap-2"
                    :class="isStockPurchaseInput ? 'sm:grid-cols-[130px_120px_100px_minmax(120px,1fr)_auto]' : 'sm:grid-cols-[130px_140px_minmax(120px,1fr)_auto]'"
                    @submit.prevent="addPurchase"
                  >
                    <input v-model="purchaseDate" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" type="date" />
                    <input v-model.number="purchaseAmount" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" min="0" step="0.01" type="number" :placeholder="purchaseAmountPlaceholder" />
                    <input v-if="isStockPurchaseInput" v-model.number="purchaseQuantity" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" min="0" step="0.0001" type="number" placeholder="数量" />
                    <input v-model="purchaseNote" class="h-9 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" placeholder="メモ" />
                    <button class="inline-flex h-9 items-center gap-1 rounded-md bg-accent px-3 text-xs font-semibold text-neutral-950 hover:bg-sky-300" type="submit">
                      <Plus :size="14" />追加
                    </button>
                  </form>
                </div>

                <div class="grid gap-3 sm:grid-cols-4">
                  <Metric label="投資額" :value="moneyValue(position.totalCost, selectedSymbol.currency)" />
                  <Metric :label="isStockPurchaseInput ? '保有数量' : '評価用数量'" :value="number(position.totalQuantity)" />
                  <Metric label="評価額" :value="moneyValue(position.marketValue, selectedSymbol.currency)" />
                  <Metric label="評価損益" :value="moneyValue(position.profitLoss, selectedSymbol.currency)" :tone="position.profitLoss" />
                </div>

                <div class="mt-3 overflow-x-auto rounded-md border border-border">
                  <table class="w-full min-w-[620px] text-left text-xs">
                    <thead class="border-b border-border text-neutral-500">
                      <tr>
                        <th class="px-3 py-2 font-medium">日付</th>
                        <th class="px-3 py-2 font-medium">購入額</th>
                        <th class="px-3 py-2 font-medium">{{ isStockPurchaseInput ? '数量' : '評価用数量' }}</th>
                        <th class="px-3 py-2 font-medium">{{ isStockPurchaseInput ? '単価' : '購入基準価額' }}</th>
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

      <section v-else-if="activeTab === 'invest-support'" class="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header class="flex flex-col gap-4 border-b border-border pb-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p class="text-sm font-medium text-accent">Pleiades</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-normal text-neutral-50 sm:text-3xl">投資支援</h1>
            <p class="mt-2 text-sm text-neutral-400">JST 1:00 に保存済みの価格履歴とカテゴリ化済み売買ルールから現在シグナルとバックテストを計算します。</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <label class="grid gap-1 text-xs text-neutral-500">
              検証年数
              <input
                v-model.number="analysisLookbackYears"
                class="h-10 w-24 rounded-md border border-border bg-panel px-3 text-sm text-neutral-100 outline-none focus:border-accent"
                type="number"
                min="1"
                max="20"
              />
            </label>
            <label class="grid gap-1 text-xs text-neutral-500">
              判定営業日
              <input
                v-model.number="analysisHorizonDays"
                class="h-10 w-24 rounded-md border border-border bg-panel px-3 text-sm text-neutral-100 outline-none focus:border-accent"
                type="number"
                min="1"
                max="260"
              />
            </label>
            <button class="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium text-neutral-100 transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-60" type="button" :disabled="analysisLoading" @click="retryInvestmentBacktest">
              <RefreshCw :size="17" :class="{ 'animate-spin': analysisLoading }" />バックテスト再試行
            </button>
          </div>
        </header>

        <p v-if="analysisLoading" class="rounded-md border border-accent/30 bg-accent/10 px-3 py-2 text-sm text-sky-100">バックエンドでバックテストを計算しています。</p>
        <p v-if="analysisError || analysis?.error" class="rounded-md border border-loss/40 bg-loss/10 px-3 py-2 text-sm text-red-200">{{ analysisError || analysis?.error }}</p>

        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="現在シグナル" :value="`${analysis?.signals.length ?? 0}件`" />
          <Metric label="平均正答率" :value="percent(analysisAccuracyAverage)" :tone="analysisAccuracyAverage === null ? undefined : analysisAccuracyAverage - 50" />
          <Metric label="平均期待騰落率" :value="percent(analysisReturnAverage)" :tone="analysisReturnAverage ?? undefined" />
          <Metric label="検証期間" :value="`${analysis?.lookback_years ?? 5}年 / ${analysis?.horizon_days ?? 20}営業日`" />
        </div>
        <div class="grid gap-5 xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
          <section id="current-signals-section" class="rounded-md border border-border bg-panel">
            <div class="flex flex-col gap-2 border-b border-border px-4 py-3">
              <div class="flex items-center justify-between gap-3">
                <h2 class="text-sm font-semibold text-neutral-200">現在シグナル</h2>
                <span class="text-xs text-neutral-500">{{ analysis?.generated_at ?? 'N/A' }}</span>
              </div>
              <label class="flex items-center gap-2 text-xs text-neutral-500">
                表示対象
                <select v-model="analysisSignalFilter" class="h-9 min-w-48 rounded-md border border-border bg-background px-2 text-xs text-neutral-100 outline-none focus:border-accent">
                  <option value="all">すべて</option>
                  <optgroup label="ルール">
                    <option v-for="rule in analysisSignalRuleOptions" :key="rule" :value="`rule:${rule}`">{{ rule }}</option>
                  </optgroup>
                  <optgroup label="区分">
                    <option v-for="side in analysisSignalSideOptions" :key="side" :value="`side:${side}`">{{ side }}</option>
                  </optgroup>
                  <optgroup label="銘柄">
                    <option v-for="symbol in analysisSignalSymbolOptions" :key="symbol.id" :value="`symbol:${symbol.id}`">{{ symbol.label }}</option>
                  </optgroup>
                </select>
              </label>
            </div>
            <div class="max-h-[560px] overflow-auto">
              <button
                v-for="signal in analysisSignals"
                :key="`${signal.symbol_id}-${signal.side}-${signal.rule_name}`"
                class="grid w-full gap-2 border-b border-border/70 px-4 py-3 text-left hover:bg-panel2"
                type="button"
                @click="selectSignalSymbolFilter(signal.symbol_id)"
              >
                <div class="flex min-w-0 items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-neutral-100">{{ signal.name }}</p>
                    <p class="mt-0.5 truncate text-xs text-neutral-500">
                      <button class="font-medium text-accent hover:text-sky-200" type="button" @click.stop="openSignalTicker(signal.symbol_id)">
                        {{ signal.ticker }}
                      </button>
                      <span> / {{ signal.rule_name }}</span>
                      <span v-if="signal.primary_category"> / {{ signal.primary_category }}</span>
                    </p>
                  </div>
                  <span class="shrink-0 rounded border px-2 py-0.5 text-xs" :class="signal.side === '買い' ? 'border-gain/40 bg-gain/10 text-gain' : 'border-loss/40 bg-loss/10 text-loss'">{{ signal.side }}</span>
                </div>
                <p class="text-xs leading-5 text-neutral-400">{{ signal.reason }}</p>
                <div class="flex flex-wrap gap-1.5">
                  <span v-if="signal.rsi_14 !== null" class="rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-neutral-300">
                    RSI(14) {{ number(signal.rsi_14) }}
                  </span>
                  <span v-if="signal.rsi_2 !== null" class="rounded border border-border bg-background px-1.5 py-0.5 text-[11px] text-neutral-300">
                    RSI(2) {{ number(signal.rsi_2) }}
                  </span>
                  <span class="rounded border border-gain/40 bg-gain/10 px-1.5 py-0.5 text-[11px] text-gain">
                    買い {{ symbolSignalStrength(signal.symbol_id).buyPercent.toFixed(0) }}% / 強さ {{ number(symbolSignalStrength(signal.symbol_id).buyStrength) }}
                  </span>
                  <span class="rounded border border-loss/40 bg-loss/10 px-1.5 py-0.5 text-[11px] text-loss">
                    売り {{ symbolSignalStrength(signal.symbol_id).sellPercent.toFixed(0) }}% / 強さ {{ number(symbolSignalStrength(signal.symbol_id).sellStrength) }}
                  </span>
                </div>
                <div class="flex h-1.5 overflow-hidden rounded bg-background">
                  <div class="h-full bg-gain" :style="{ width: `${symbolSignalStrength(signal.symbol_id).buyPercent}%` }"></div>
                  <div class="h-full bg-loss" :style="{ width: `${symbolSignalStrength(signal.symbol_id).sellPercent}%` }"></div>
                </div>
                <div class="flex items-center justify-between text-xs text-neutral-500">
                  <span>{{ signal.date }}</span>
                  <span>{{ money(signal.close, null) }}</span>
                </div>
              </button>
              <div v-if="analysisSignals.length === 0" class="px-4 py-10 text-center text-sm text-neutral-500">現在該当する銘柄はありません</div>
            </div>
          </section>

          <div class="grid min-w-0 gap-5">
            <section class="min-w-0 rounded-md border border-border bg-panel">
              <div class="flex flex-col gap-2 border-b border-border px-4 py-3 md:flex-row md:items-center md:justify-between">
                <button class="inline-flex items-center gap-2 text-left" type="button" @click="categoryBacktestOpen = !categoryBacktestOpen">
                  <h2 class="text-sm font-semibold text-neutral-200">カテゴリ別バックテスト</h2>
                  <ChevronUp v-if="categoryBacktestOpen" class="text-neutral-500" :size="15" />
                  <ChevronDown v-else class="text-neutral-500" :size="15" />
                </button>
                <div class="flex rounded-md border border-border bg-background p-1">
                  <button
                    v-for="side in analysisSideFilters"
                    :key="side"
                    type="button"
                    class="h-8 rounded px-3 text-xs font-medium transition"
                    :class="analysisSideFilter === side ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                    @click="analysisSideFilter = side"
                  >
                    {{ side }}
                  </button>
                </div>
              </div>
              <div v-if="categoryBacktestOpen" class="overflow-x-auto">
                <table class="w-full min-w-[1200px] text-left text-sm">
                  <thead class="border-b border-border text-xs text-neutral-500">
                    <tr>
                      <th v-for="column in analysisCategoryColumns" :key="column.value" class="px-4 py-2 font-medium" :class="column.class">
                        <button class="inline-flex items-center gap-1 rounded px-1 py-1 hover:bg-panel2 hover:text-neutral-200" :class="column.align === 'right' ? 'ml-auto' : ''" type="button" @click="setAnalysisCategorySort(column.value)">
                          {{ column.label }}
                          <ArrowUpDown :size="12" :class="analysisCategorySort === column.value ? 'text-accent' : 'text-neutral-600'" />
                          <span v-if="analysisCategorySort === column.value" class="text-accent">{{ analysisCategorySortMark }}</span>
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <template v-for="category in filteredAnalysisCategories" :key="`${category.side}-${category.name}`">
                      <tr class="border-b border-border/70 align-top hover:bg-background/70">
                        <td class="px-4 py-3">
                          <span class="rounded border px-2 py-0.5 text-xs" :class="category.side === '買い' ? 'border-gain/40 bg-gain/10 text-gain' : 'border-loss/40 bg-loss/10 text-loss'">{{ category.side }}</span>
                        </td>
                        <td class="px-4 py-3">
                          <button class="flex w-full items-start justify-between gap-2 text-left" type="button" @click="toggleAnalysisCategoryDetail(category)">
                            <span class="block font-semibold text-neutral-100">{{ category.category_a ?? category.name }}</span>
                            <ChevronUp v-if="isAnalysisCategoryExpanded(category)" class="mt-0.5 shrink-0 text-neutral-500" :size="14" />
                            <ChevronDown v-else class="mt-0.5 shrink-0 text-neutral-500" :size="14" />
                          </button>
                        </td>
                        <td class="px-4 py-3 font-semibold text-neutral-100">{{ category.category_b ?? '-' }}</td>
                        <td class="px-4 py-3">
                          <p class="text-xs leading-5 text-neutral-300">{{ category.relation ?? '-' }}</p>
                        </td>
                        <td class="px-4 py-3 text-right text-neutral-300">{{ category.rule_count }}</td>
                        <td class="px-4 py-3 text-right">
                          <button
                            class="rounded px-1.5 py-0.5 text-neutral-100 hover:bg-panel2 hover:text-accent disabled:cursor-default disabled:text-neutral-500 disabled:hover:bg-transparent"
                            type="button"
                            :disabled="category.current_signal_count === 0"
                            @click="toggleAnalysisCategorySignals(category)"
                          >
                            {{ category.current_signal_count }}
                          </button>
                        </td>
                        <td class="px-4 py-3 text-right text-neutral-300">{{ number(categorySignalStrength(category)) }}</td>
                        <td class="px-4 py-3 text-right text-neutral-300">{{ category.backtest.signals }}</td>
                        <td class="px-4 py-3 text-right" :class="percentClass(category.backtest.accuracy_percent === null ? null : category.backtest.accuracy_percent - 50)">{{ percent(category.backtest.accuracy_percent) }}</td>
                        <td class="px-4 py-3 text-right" :class="percentClass(category.backtest.average_return_percent)">{{ percent(category.backtest.average_return_percent) }}</td>
                        <td class="px-4 py-3 text-right" :class="percentClass(category.interaction_effect_return_percent)">{{ percent(category.interaction_effect_return_percent) }}</td>
                      </tr>
                      <tr v-if="isAnalysisCategorySignalsExpanded(category)" class="border-b border-border/70 bg-background/60">
                        <td colspan="11" class="px-4 py-3">
                          <div class="mb-2 text-xs font-semibold text-neutral-300">該当銘柄</div>
                          <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                            <button
                              v-for="symbol in analysisCategoryCurrentSymbols(category)"
                              :key="symbol.symbol_id"
                              class="grid gap-1 rounded-md border border-border bg-panel px-3 py-2 text-left hover:border-accent hover:bg-panel2"
                              type="button"
                              @click="openCategoryCurrentSymbol(symbol.symbol_id)"
                            >
                              <span class="truncate text-sm font-semibold text-neutral-100">{{ symbol.name }}</span>
                              <span class="flex items-center justify-between gap-2 text-xs text-neutral-500">
                                <span class="truncate text-accent">{{ symbol.ticker }}</span>
                                <span>{{ money(symbol.close, null) }}</span>
                              </span>
                              <span class="text-xs text-neutral-500">{{ symbol.signal_count }}件の現在シグナル</span>
                            </button>
                          </div>
                          <div v-if="analysisCategoryCurrentSymbols(category).length === 0" class="py-4 text-center text-sm text-neutral-500">該当銘柄はありません</div>
                        </td>
                      </tr>
                      <tr v-if="isAnalysisCategoryExpanded(category)" class="border-b border-border/70 bg-background/50">
                        <td colspan="11" class="px-4 py-4">
                          <div class="mb-4 grid gap-3 text-xs text-neutral-400 sm:grid-cols-3">
                            <div>
                              <p class="text-neutral-500">カテゴリA単独 期待騰落率</p>
                              <p class="mt-1 text-sm font-semibold text-neutral-100">{{ percent(category.baseline_backtest?.average_return_percent ?? null) }}</p>
                            </div>
                            <div>
                              <p class="text-neutral-500">カテゴリA単独 検証数</p>
                              <p class="mt-1 text-sm font-semibold text-neutral-100">{{ category.baseline_backtest?.signals ?? 0 }}</p>
                            </div>
                            <div>
                              <p class="text-neutral-500">マトリクス重み</p>
                              <p class="mt-1 text-sm font-semibold text-neutral-100">{{ category.matrix_weight === null ? '-' : number(category.matrix_weight) }}</p>
                            </div>
                          </div>
                          <div class="mb-3 text-xs font-semibold text-neutral-300">曜日分析</div>
                          <div class="overflow-x-auto rounded-md border border-border">
                            <table class="w-full min-w-[900px] text-left text-xs">
                              <thead class="border-b border-border text-neutral-500">
                                <tr>
                                  <th class="w-16 px-3 py-2 font-medium">曜日</th>
                                  <th class="w-24 px-3 py-2 text-right font-medium">シグナル数</th>
                                  <th class="w-28 px-3 py-2 text-right font-medium">発生日</th>
                                  <th class="w-28 px-3 py-2 text-right font-medium">1日後</th>
                                  <th class="w-28 px-3 py-2 text-right font-medium">3日後</th>
                                  <th class="w-28 px-3 py-2 text-right font-medium">5日後</th>
                                  <th class="w-36 px-3 py-2 text-right font-medium">交互作用</th>
                                  <th class="w-28 px-3 py-2 text-right font-medium">SQ週数</th>
                                  <th class="w-36 px-3 py-2 text-right font-medium">SQ週交互作用</th>
                                </tr>
                              </thead>
                              <tbody>
                                <tr v-for="stat in category.weekday_stats" :key="stat.weekday" class="border-b border-border/70">
                                  <td class="px-3 py-2 font-semibold text-neutral-100">{{ stat.label }}</td>
                                  <td class="px-3 py-2 text-right text-neutral-300">{{ stat.signal_count }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.signal_day_average_return_percent)">{{ percent(stat.signal_day_average_return_percent) }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_1d_percent)">{{ percent(stat.average_return_1d_percent) }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_3d_percent)">{{ percent(stat.average_return_3d_percent) }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_5d_percent)">{{ percent(stat.average_return_5d_percent) }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.interaction_effect_1d_percent)">{{ percent(stat.interaction_effect_1d_percent) }}</td>
                                  <td class="px-3 py-2 text-right text-neutral-300">{{ stat.major_sq_week_signal_count }}</td>
                                  <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_interaction_effect_1d_percent)">{{ percent(stat.major_sq_week_interaction_effect_1d_percent) }}</td>
                                </tr>
                                <tr v-if="category.weekday_stats.length === 0">
                                  <td colspan="9" class="px-3 py-5 text-center text-neutral-500">曜日分析データはありません</td>
                                </tr>
                              </tbody>
                            </table>
                          </div>
                        </td>
                      </tr>
                    </template>
                    <tr v-if="filteredAnalysisCategories.length === 0">
                      <td colspan="11" class="px-4 py-8 text-center text-sm text-neutral-500">カテゴリはありません</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

          <section class="min-w-0 rounded-md border border-border bg-panel">
            <div class="flex flex-col gap-2 border-b border-border px-4 py-3 md:flex-row md:items-center md:justify-between">
              <button class="inline-flex items-center gap-2 text-left" type="button" @click="ruleBacktestOpen = !ruleBacktestOpen">
                <h2 class="text-sm font-semibold text-neutral-200">ルール別バックテスト</h2>
                <ChevronUp v-if="ruleBacktestOpen" class="text-neutral-500" :size="15" />
                <ChevronDown v-else class="text-neutral-500" :size="15" />
              </button>
              <div class="flex rounded-md border border-border bg-background p-1">
                <button
                  v-for="side in analysisSideFilters"
                  :key="side"
                  type="button"
                  class="h-8 rounded px-3 text-xs font-medium transition"
                  :class="analysisSideFilter === side ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                  @click="analysisSideFilter = side"
                >
                  {{ side }}
                </button>
              </div>
            </div>
            <div v-if="ruleBacktestOpen" class="overflow-x-auto">
              <table class="w-full min-w-[1040px] text-left text-sm">
                <thead class="border-b border-border text-xs text-neutral-500">
                  <tr>
                    <th v-for="column in analysisRuleColumns" :key="column.value" class="px-4 py-2 font-medium" :class="column.class">
                      <button class="inline-flex items-center gap-1 rounded px-1 py-1 hover:bg-panel2 hover:text-neutral-200" :class="column.align === 'right' ? 'ml-auto' : ''" type="button" @click="setAnalysisRuleSort(column.value)">
                        {{ column.label }}
                        <ArrowUpDown :size="12" :class="analysisRuleSort === column.value ? 'text-accent' : 'text-neutral-600'" />
                        <span v-if="analysisRuleSort === column.value" class="text-accent">{{ analysisRuleSortMark }}</span>
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="rule in filteredAnalysisRules" :key="`${rule.side}-${rule.name}`">
                    <tr class="border-b border-border/70 align-top hover:bg-background/70">
                      <td class="px-4 py-3">
                        <span class="rounded border px-2 py-0.5 text-xs" :class="rule.side === '買い' ? 'border-gain/40 bg-gain/10 text-gain' : 'border-loss/40 bg-loss/10 text-loss'">{{ rule.side }}</span>
                      </td>
                      <td class="px-4 py-3">
                        <button class="flex w-full items-start justify-between gap-2 text-left" type="button" @click="toggleAnalysisRuleDetail(rule)">
                          <span class="min-w-0">
                            <span class="block font-semibold text-neutral-100">{{ rule.name }}</span>
                            <span v-if="!rule.supported" class="mt-1 block text-xs text-neutral-500">ペア取引は銘柄ペア定義未実装</span>
                          </span>
                          <ChevronUp v-if="isAnalysisRuleExpanded(rule)" class="mt-0.5 shrink-0 text-neutral-500" :size="14" />
                          <ChevronDown v-else class="mt-0.5 shrink-0 text-neutral-500" :size="14" />
                        </button>
                      </td>
                      <td class="px-4 py-3">
                        <p class="text-xs leading-5 text-neutral-300">{{ rule.condition }}</p>
                        <p class="mt-1 text-xs leading-5 text-neutral-500">{{ rule.description }}</p>
                      </td>
                      <td class="px-4 py-3 text-right">
                        <button class="rounded px-1.5 py-0.5 text-neutral-100 hover:bg-panel2 hover:text-accent" type="button" @click="selectSignalRuleFilter(rule.name)">
                          {{ rule.current_signal_count }}
                        </button>
                      </td>
                      <td class="px-4 py-3 text-right text-neutral-300">{{ number(ruleSignalStrength(rule)) }}</td>
                      <td class="px-4 py-3 text-right text-neutral-300">{{ rule.backtest.signals }}</td>
                      <td class="px-4 py-3 text-right" :class="percentClass(rule.backtest.accuracy_percent === null ? null : rule.backtest.accuracy_percent - 50)">{{ percent(rule.backtest.accuracy_percent) }}</td>
                      <td class="px-4 py-3 text-right" :class="percentClass(rule.backtest.average_return_percent)">{{ percent(rule.backtest.average_return_percent) }}</td>
                      <td class="px-4 py-3 text-right text-neutral-300">{{ percent(rule.backtest.average_abs_return_percent) }}</td>
                    </tr>
                    <tr v-if="isAnalysisRuleExpanded(rule)" class="border-b border-border/70 bg-background/50">
                      <td colspan="9" class="px-4 py-4">
                        <div class="mb-3 text-xs font-semibold text-neutral-300">曜日分析</div>
                        <div class="overflow-x-auto rounded-md border border-border">
                          <table class="w-full min-w-[1280px] text-left text-xs">
                            <thead class="border-b border-border text-neutral-500">
                              <tr>
                                <th class="w-16 px-3 py-2 font-medium">曜日</th>
                                <th class="w-24 px-3 py-2 text-right font-medium">全体件数</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">全体日次</th>
                                <th class="w-24 px-3 py-2 text-right font-medium">シグナル数</th>
                                <th class="w-32 px-3 py-2 text-right font-medium">発生日</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">1日後</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">3日後</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">5日後</th>
                                <th class="w-36 px-3 py-2 text-right font-medium">交互作用</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">SQ週全体</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">SQ週数</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">SQ週1日後</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">SQ週3日後</th>
                                <th class="w-28 px-3 py-2 text-right font-medium">SQ週5日後</th>
                                <th class="w-36 px-3 py-2 text-right font-medium">SQ週交互作用</th>
                              </tr>
                            </thead>
                            <tbody>
                              <tr v-for="stat in rule.weekday_stats" :key="stat.weekday" class="border-b border-border/70">
                                <td class="px-3 py-2 font-semibold text-neutral-100">{{ stat.label }}</td>
                                <td class="px-3 py-2 text-right text-neutral-300">{{ stat.market_sample_count }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.market_average_daily_return_percent)">{{ percent(stat.market_average_daily_return_percent) }}</td>
                                <td class="px-3 py-2 text-right text-neutral-300">{{ stat.signal_count }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.signal_day_average_return_percent)">{{ percent(stat.signal_day_average_return_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_1d_percent)">{{ percent(stat.average_return_1d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_3d_percent)">{{ percent(stat.average_return_3d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.average_return_5d_percent)">{{ percent(stat.average_return_5d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.interaction_effect_1d_percent)">{{ percent(stat.interaction_effect_1d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_market_average_daily_return_percent)">{{ percent(stat.major_sq_week_market_average_daily_return_percent) }}</td>
                                <td class="px-3 py-2 text-right text-neutral-300">{{ stat.major_sq_week_signal_count }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_average_return_1d_percent)">{{ percent(stat.major_sq_week_average_return_1d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_average_return_3d_percent)">{{ percent(stat.major_sq_week_average_return_3d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_average_return_5d_percent)">{{ percent(stat.major_sq_week_average_return_5d_percent) }}</td>
                                <td class="px-3 py-2 text-right" :class="percentClass(stat.major_sq_week_interaction_effect_1d_percent)">{{ percent(stat.major_sq_week_interaction_effect_1d_percent) }}</td>
                              </tr>
                              <tr v-if="rule.weekday_stats.length === 0">
                                <td colspan="15" class="px-3 py-5 text-center text-neutral-500">曜日分析データはありません</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  </template>
                  <tr v-if="filteredAnalysisRules.length === 0">
                    <td colspan="9" class="px-4 py-8 text-center text-sm text-neutral-500">ルールはありません</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'household'" class="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header class="flex flex-col gap-4 border-b border-border pb-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p class="text-sm font-medium text-accent">Pleiades</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-normal text-neutral-50 sm:text-3xl">家計簿</h1>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select v-model="householdMonth" class="h-10 rounded-md border border-border bg-panel px-3 text-sm outline-none focus:border-accent" @change="setHouseholdMonth(householdMonth)">
              <option value="">全期間</option>
              <option v-for="month in householdMonthOptions" :key="month" :value="month">{{ month }}</option>
            </select>
            <button class="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium text-neutral-100 transition hover:border-accent" type="button" :disabled="householdLoading" @click="loadHousehold">
              <RefreshCw :size="17" :class="{ 'animate-spin': householdLoading }" />再読込
            </button>
            <input ref="householdFileInput" class="hidden" type="file" accept=".csv,text/csv" multiple @change="uploadHouseholdCsv" />
            <button class="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium text-neutral-100 transition hover:border-accent disabled:cursor-not-allowed disabled:opacity-60" type="button" :disabled="householdImporting" @click="householdFileInput?.click()">
              <Upload :size="17" />CSV取込
            </button>
            <button class="inline-flex h-10 items-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-sky-300 disabled:cursor-not-allowed disabled:opacity-60" type="button" :disabled="householdImporting" @click="importHouseholdSampleData">
              <Plus :size="17" />サンプル取込
            </button>
          </div>
        </header>

        <p v-if="householdError" class="rounded-md border px-3 py-2 text-sm" :class="householdError.includes('取り込み') || householdError.includes('スキップ') ? 'border-accent/30 bg-accent/10 text-sky-100' : 'border-loss/40 bg-loss/10 text-red-200'">{{ householdError }}</p>

        <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric label="対象期間" :value="householdSelectedMonthLabel" />
          <Metric label="収入" :value="moneyValue(household?.total_income ?? 0, 'JPY')" :tone="household?.total_income ?? 0" />
          <Metric label="支出" :value="moneyValue(household?.total_expense ?? 0, 'JPY')" :tone="-1" />
          <Metric label="収支" :value="moneyValue(household?.net ?? 0, 'JPY')" :tone="household?.net ?? 0" />
        </div>

        <section class="rounded-md border border-border bg-panel">
          <div class="flex flex-col gap-1 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 class="text-sm font-semibold text-neutral-200">資産推移</h2>
            <span class="text-xs text-neutral-500">{{ householdAssetPoints.length }}点</span>
          </div>
          <div class="p-4">
            <div v-if="householdAssetChart.points.length >= 2" class="h-64 w-full">
              <svg class="h-full w-full overflow-visible" viewBox="0 0 720 220" role="img">
                <line x1="48" y1="14" x2="48" y2="184" stroke="#2a3036" />
                <line x1="48" y1="184" x2="704" y2="184" stroke="#2a3036" />
                <path :d="householdAssetChart.areaPath" fill="rgba(125, 211, 252, 0.10)" />
                <path :d="householdAssetChart.linePath" fill="none" stroke="#7dd3fc" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
                <circle
                  v-for="point in householdAssetChart.points"
                  :key="point.date"
                  :cx="point.x"
                  :cy="point.y"
                  r="3"
                  fill="#101214"
                  stroke="#7dd3fc"
                  stroke-width="2"
                >
                  <title>{{ point.date }} {{ moneyValue(point.balance, 'JPY') }}</title>
                </circle>
                <text x="48" y="207" fill="#8b949e" font-size="12">{{ householdAssetChart.firstDate }}</text>
                <text x="704" y="207" fill="#8b949e" font-size="12" text-anchor="end">{{ householdAssetChart.lastDate }}</text>
                <text x="42" y="18" fill="#8b949e" font-size="12" text-anchor="end">{{ compact(householdAssetChart.maxBalance) }}</text>
                <text x="42" y="188" fill="#8b949e" font-size="12" text-anchor="end">{{ compact(householdAssetChart.minBalance) }}</text>
              </svg>
            </div>
            <div v-else class="flex h-40 items-center justify-center text-sm text-neutral-500">銀行明細の残高データが不足しています</div>
          </div>
        </section>

        <div class="grid gap-5 xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]">
          <div class="grid gap-5">
            <section class="rounded-md border border-border bg-panel">
              <div class="border-b border-border px-4 py-3">
                <h2 class="text-sm font-semibold text-neutral-200">支出カテゴリ</h2>
              </div>
              <div class="grid gap-3 p-4">
                <div v-for="category in householdCategories" :key="category.category" class="grid gap-1">
                  <div class="flex items-center justify-between gap-3 text-sm">
                    <span class="truncate font-medium text-neutral-100">{{ category.category }}</span>
                    <span class="shrink-0 text-neutral-300">{{ moneyValue(category.expense, 'JPY') }}</span>
                  </div>
                  <div class="h-2 overflow-hidden rounded bg-background">
                    <div class="h-full bg-accent" :style="{ width: `${category.share_percent ?? 0}%` }"></div>
                  </div>
                  <div class="flex justify-between text-xs text-neutral-500">
                    <span>{{ category.transaction_count }}件</span>
                    <span>{{ percent(category.share_percent) }}</span>
                  </div>
                </div>
                <p v-if="householdCategories.length === 0" class="py-6 text-center text-sm text-neutral-500">カテゴリ集計はありません</p>
              </div>
            </section>

            <section class="rounded-md border border-border bg-panel">
              <div class="border-b border-border px-4 py-3">
                <h2 class="text-sm font-semibold text-neutral-200">月次推移</h2>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[420px] text-left text-sm">
                  <thead class="border-b border-border text-xs text-neutral-500">
                    <tr>
                      <th class="px-4 py-2 font-medium">月</th>
                      <th class="px-4 py-2 text-right font-medium">収入</th>
                      <th class="px-4 py-2 text-right font-medium">支出</th>
                      <th class="px-4 py-2 text-right font-medium">収支</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="row in householdMonthlyDesc" :key="row.month" class="border-b border-border/70">
                      <td class="px-4 py-2">
                        <button class="font-medium text-accent hover:text-sky-200" type="button" @click="setHouseholdMonth(row.month)">{{ row.month }}</button>
                      </td>
                      <td class="px-4 py-2 text-right text-neutral-300">{{ moneyValue(row.income, 'JPY') }}</td>
                      <td class="px-4 py-2 text-right text-neutral-300">{{ moneyValue(row.expense, 'JPY') }}</td>
                      <td class="px-4 py-2 text-right" :class="row.net >= 0 ? 'text-gain' : 'text-loss'">{{ moneyValue(row.net, 'JPY') }}</td>
                    </tr>
                    <tr v-if="householdMonthlyDesc.length === 0">
                      <td colspan="4" class="px-4 py-6 text-center text-sm text-neutral-500">月次データはありません</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section class="min-w-0 rounded-md border border-border bg-panel">
            <div class="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 class="text-sm font-semibold text-neutral-200">明細</h2>
                <p class="mt-1 text-xs text-neutral-500">最大支出: {{ household?.largest_expense ? `${household.largest_expense.transacted_at} ${household.largest_expense.merchant} ${moneyValue(household.largest_expense.amount, 'JPY')}` : 'N/A' }}</p>
              </div>
              <span class="text-xs text-neutral-500">{{ householdTransactions.length }}件</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[980px] table-fixed text-left text-sm">
                <thead class="border-b border-border text-xs text-neutral-500">
                  <tr>
                    <th class="w-28 px-3 py-2 font-medium">日付</th>
                    <th class="w-28 px-3 py-2 text-right font-medium">金額</th>
                    <th class="w-40 px-3 py-2 font-medium">カテゴリ</th>
                    <th class="w-[24%] px-3 py-2 font-medium">利用先</th>
                    <th class="px-3 py-2 font-medium">内容</th>
                    <th class="w-20 px-3 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="transaction in householdTransactions" :key="transaction.id" class="border-b border-border/70 align-top hover:bg-background/70">
                    <td class="px-3 py-3 text-neutral-300">{{ transaction.transacted_at }}</td>
                    <td class="px-3 py-3 text-right font-semibold" :class="transaction.direction === 'income' ? 'text-gain' : 'text-neutral-100'">
                      {{ transaction.direction === 'income' ? '+' : '-' }}{{ moneyValue(transaction.amount, 'JPY') }}
                    </td>
                    <td class="px-3 py-3">
                      <select class="h-8 w-full rounded-md border border-border bg-panel px-2 text-xs outline-none focus:border-accent" :value="transaction.category" @change="changeHouseholdCategory(transaction, ($event.target as HTMLSelectElement).value)">
                        <option v-for="category in householdCategoryOptions" :key="category" :value="category">{{ category }}</option>
                      </select>
                    </td>
                    <td class="px-3 py-3">
                      <p class="truncate font-medium text-neutral-100" :title="transaction.merchant">{{ transaction.merchant || '-' }}</p>
                      <p class="mt-1 text-xs text-neutral-500">{{ transaction.source_type }}</p>
                    </td>
                    <td class="px-3 py-3">
                      <p class="line-clamp-2 text-xs leading-5 text-neutral-400" :title="transaction.description">{{ transaction.description }}</p>
                    </td>
                    <td class="px-3 py-3">
                      <button class="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-xs font-medium text-neutral-300 hover:border-accent hover:text-accent" type="button" @click="toggleHouseholdExcluded(transaction)">
                        <X :size="13" />除外
                      </button>
                    </td>
                  </tr>
                  <tr v-if="householdTransactions.length === 0">
                    <td colspan="6" class="px-4 py-10 text-center text-sm text-neutral-500">明細はありません</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </section>

      <section v-else-if="activeTab === 'tasks'" class="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8">
        <header class="flex flex-col gap-4 border-b border-border pb-5 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p class="text-sm font-medium text-accent">Pleiades</p>
            <h1 class="mt-1 text-2xl font-semibold tracking-normal text-neutral-50 sm:text-3xl">タスク管理</h1>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <div class="flex rounded-md border border-border bg-panel p-1">
              <button
                v-for="option in taskSortOptions"
                :key="option.value"
                type="button"
                class="inline-flex h-9 items-center gap-1.5 rounded px-3 text-xs font-medium transition"
                :class="taskSort === option.value ? 'bg-panel2 text-accent' : 'text-neutral-400 hover:text-neutral-100'"
                @click="setTaskSort(option.value)"
              >
                <ArrowUpDown :size="14" />{{ option.label }}{{ taskSort === option.value ? taskSortMark : '' }}
              </button>
            </div>
            <button class="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-panel px-3 text-sm font-medium text-neutral-100 transition hover:border-accent" type="button" @click="loadTaskData">
              <RefreshCw :size="17" />再読込
            </button>
          </div>
        </header>

        <p v-if="taskError" class="rounded-md border border-loss/40 bg-loss/10 px-3 py-2 text-sm text-red-200">{{ taskError }}</p>

        <div class="grid gap-5 xl:grid-cols-[minmax(280px,360px)_minmax(0,1fr)]">
          <section class="rounded-md border border-border bg-panel">
            <div class="border-b border-border px-4 py-3">
              <h2 class="text-sm font-semibold text-neutral-200">{{ editingTask ? 'タスク編集' : 'タスク追加' }}</h2>
            </div>
            <form class="grid gap-3 p-4" @submit.prevent="saveTask">
              <input v-model="taskTitle" class="h-10 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-accent" placeholder="名前" />
              <div class="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
                <select v-model="taskStatus" class="h-10 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-accent">
                  <option value="todo">開始前</option>
                  <option value="doing">進行中</option>
                  <option value="done">完了</option>
                </select>
                <input v-model="taskDueDate" class="h-10 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-accent" type="date" />
              </div>
              <input v-model.number="taskDurationDays" class="h-10 rounded-md border border-border bg-background px-3 text-sm outline-none focus:border-accent" min="0" step="1" type="number" placeholder="継続期間（日）" />
              <textarea v-model="taskDetails" class="min-h-28 resize-y rounded-md border border-border bg-background px-3 py-2 text-sm outline-none focus:border-accent" placeholder="詳細"></textarea>
              <div class="flex flex-wrap gap-2">
                <label
                  v-for="tag in taskTags"
                  :key="tag.id"
                  class="inline-flex h-8 cursor-pointer items-center gap-2 rounded border border-border px-2 text-xs text-neutral-200"
                  :class="selectedTaskTagIds.includes(tag.id) ? 'bg-panel2' : 'bg-background opacity-70'"
                >
                  <input v-model="selectedTaskTagIds" class="sr-only" type="checkbox" :value="tag.id" />
                  <span class="h-2.5 w-2.5 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                  <span>{{ tag.name }}</span>
                </label>
              </div>
              <div class="flex gap-2">
                <button class="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-md bg-accent px-3 text-sm font-semibold text-neutral-950 transition hover:bg-sky-300" type="submit">
                  <Plus v-if="!editingTask" :size="17" />
                  <CheckCircle2 v-else :size="17" />
                  {{ editingTask ? '保存' : '追加' }}
                </button>
                <button v-if="editingTask" class="h-10 rounded-md border border-border px-3 text-sm font-medium text-neutral-200 hover:border-accent" type="button" @click="resetTaskForm">取消</button>
              </div>
            </form>

            <div class="border-t border-border px-4 py-3">
              <h2 class="text-sm font-semibold text-neutral-200">タグ</h2>
            </div>
            <form class="grid grid-cols-[1fr_44px_auto] gap-2 px-4 pb-4" @submit.prevent="addTaskTag">
              <input v-model="newTaskTagName" class="h-9 min-w-0 rounded-md border border-border bg-background px-2 text-xs outline-none focus:border-accent" placeholder="タグ名" />
              <input v-model="newTaskTagColor" class="h-9 w-11 rounded-md border border-border bg-background p-1" type="color" />
              <button class="inline-flex h-9 items-center gap-1 rounded-md border border-border px-2 text-xs font-medium text-neutral-200 hover:border-accent" type="submit">
                <Plus :size="14" />追加
              </button>
            </form>
            <div class="grid gap-2 px-4 pb-4">
              <div v-for="tag in taskTags" :key="tag.id" class="grid grid-cols-[auto_1fr_auto_auto] items-center gap-2 rounded-md border border-border bg-background px-2 py-2">
                <span class="h-3 w-3 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                <span class="truncate text-sm" :class="tag.hidden ? 'text-neutral-500' : 'text-neutral-200'">{{ tag.name }}</span>
                <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-accent hover:text-accent" type="button" :title="tag.hidden ? '表示' : '非表示'" @click="toggleTaskTagHidden(tag)">
                  <EyeOff :size="14" />
                </button>
                <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-loss hover:text-loss" type="button" title="削除" @click="removeTaskTag(tag)">
                  <Trash2 :size="14" />
                </button>
              </div>
              <p v-if="taskTags.length === 0" class="text-sm text-neutral-500">タグはありません</p>
            </div>
          </section>

          <section class="min-w-0 rounded-md border border-border bg-panel">
            <div class="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 class="text-sm font-semibold text-neutral-200">一覧</h2>
              <span class="text-xs text-neutral-500">{{ visibleTasks.length }}件</span>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[940px] table-fixed text-left text-sm">
                <thead class="border-b border-border text-xs text-neutral-500">
                  <tr>
                    <th v-for="column in taskTableColumns" :key="column.value" class="px-3 py-2 font-medium" :class="column.class">
                      <button class="inline-flex items-center gap-1 rounded px-1 py-1 hover:bg-panel2 hover:text-neutral-200" type="button" @click="setTaskSort(column.value)">
                        {{ column.label }}
                        <ArrowUpDown :size="12" :class="taskSort === column.value ? 'text-accent' : 'text-neutral-600'" />
                        <span v-if="taskSort === column.value" class="text-accent">{{ taskSortMark }}</span>
                      </button>
                    </th>
                    <th class="w-24 px-3 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="task in activeTasks" :key="task.id" class="border-b border-border/70 align-top hover:bg-background/70">
                    <td class="px-3 py-3">
                      <button class="block w-full truncate text-left font-semibold text-neutral-100 hover:text-accent" type="button" @click="editTask(task)">
                        {{ task.title }}
                      </button>
                    </td>
                    <td class="px-3 py-3">
                      <select class="h-8 w-full rounded-md border border-border bg-panel px-2 text-xs outline-none focus:border-accent" :value="task.status" @change="changeTaskStatus(task, ($event.target as HTMLSelectElement).value as TaskStatus)">
                        <option value="todo">開始前</option>
                        <option value="doing">進行中</option>
                        <option value="done">完了</option>
                      </select>
                    </td>
                    <td class="px-3 py-3 text-neutral-300">{{ task.due_date ?? '' }}</td>
                    <td class="px-3 py-3 text-right text-neutral-300">{{ task.duration_days === null ? '' : `${task.duration_days}日` }}</td>
                    <td class="px-3 py-3">
                      <div class="flex flex-wrap gap-1">
                        <span v-for="tag in task.tags" :key="tag.id" class="inline-flex max-w-full items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-neutral-300">
                          <span class="h-2 w-2 shrink-0 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                          <span class="truncate">{{ tag.name }}</span>
                        </span>
                      </div>
                    </td>
                    <td class="px-3 py-3">
                      <button class="line-clamp-2 w-full text-left text-xs text-neutral-400 hover:text-accent" type="button" @click="editTask(task)">
                        {{ task.details || '詳細なし' }}
                      </button>
                    </td>
                    <td class="px-3 py-3">
                      <div class="flex items-center justify-end gap-2">
                        <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-accent hover:text-accent" type="button" title="編集" @click="editTask(task)">
                          <CheckCircle2 :size="14" />
                        </button>
                        <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-loss hover:text-loss" type="button" title="削除" @click="removeTask(task)">
                          <Trash2 :size="14" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="activeTasks.length === 0">
                    <td colspan="7" class="px-4 py-8 text-center text-sm text-neutral-500">未完了タスクはありません</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="border-t border-border px-4 py-3">
              <h2 class="text-sm font-semibold text-neutral-200">完了</h2>
            </div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[780px] table-fixed text-left text-sm">
                <thead class="border-b border-border text-xs text-neutral-500">
                  <tr>
                    <th class="w-[24%] px-3 py-2 font-medium">名前</th>
                    <th class="w-36 px-3 py-2 font-medium">完了日時</th>
                    <th class="w-28 px-3 py-2 font-medium">期限</th>
                    <th class="w-[22%] px-3 py-2 font-medium">タグ</th>
                    <th class="px-3 py-2 font-medium">詳細</th>
                    <th class="w-24 px-3 py-2 font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="task in completedTasks" :key="task.id" class="border-b border-border/70 align-top hover:bg-background/70">
                    <td class="px-3 py-3">
                      <button class="block w-full truncate text-left font-semibold text-neutral-300 hover:text-accent" type="button" @click="editTask(task)">
                        {{ task.title }}
                      </button>
                    </td>
                    <td class="px-3 py-3 text-xs text-neutral-500">{{ formatDateTime(task.completed_at) }}</td>
                    <td class="px-3 py-3 text-neutral-400">{{ task.due_date ?? '' }}</td>
                    <td class="px-3 py-3">
                      <div class="flex flex-wrap gap-1">
                        <span v-for="tag in task.tags" :key="tag.id" class="inline-flex max-w-full items-center gap-1 rounded border border-border px-1.5 py-0.5 text-[11px] text-neutral-400">
                          <span class="h-2 w-2 shrink-0 rounded-full" :style="{ backgroundColor: tag.color }"></span>
                          <span class="truncate">{{ tag.name }}</span>
                        </span>
                      </div>
                    </td>
                    <td class="px-3 py-3">
                      <button class="line-clamp-2 w-full text-left text-xs text-neutral-500 hover:text-accent" type="button" @click="editTask(task)">
                        {{ task.details || '詳細なし' }}
                      </button>
                    </td>
                    <td class="px-3 py-3">
                      <div class="flex items-center justify-end gap-2">
                        <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-accent hover:text-accent" type="button" title="再開" @click="changeTaskStatus(task, 'doing')">
                          <RefreshCw :size="13" />
                        </button>
                        <button class="flex h-8 w-8 items-center justify-center rounded-md border border-border text-neutral-400 hover:border-loss hover:text-loss" type="button" title="削除" @click="removeTask(task)">
                          <Trash2 :size="13" />
                        </button>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="completedTasks.length === 0">
                    <td colspan="6" class="px-4 py-6 text-center text-sm text-neutral-500">完了タスクはありません</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </div>
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
  ArrowUpDown,
  BarChart3,
  BriefcaseBusiness,
  ChartCandlestick,
  ChartLine,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CreditCard,
  EyeOff,
  GripVertical,
  Home,
  Layers,
  Menu,
  Plus,
  RefreshCw,
  Tag,
  Trash2,
  Upload,
  X
} from '@lucide/vue'
import SparklineChart from './components/SparklineChart.vue'
import {
  createSymbol,
  createTask,
  createTaskTag,
  cancelRefreshJob,
  createPurchase,
  deleteSymbol,
  deletePurchase,
  deleteTask,
  deleteTaskTag,
  getHouseholdAnalysis,
  getHistory,
  getInvestmentAnalysis,
  importHouseholdCsv,
  importHouseholdSamples,
  listRefreshJobs,
  listPurchases,
  listSymbols,
  listTaskTags,
  listTasks,
  recalculateInvestmentAnalysis,
  reorderSymbols,
  refreshAll,
  refreshSymbol,
  updateTask,
  updateTaskTag,
  updateHouseholdTransaction,
  updateSymbol,
  type HouseholdAnalysis,
  type HouseholdTransaction,
  type PricePoint,
  type Purchase,
  type AnalysisCategory,
  type AnalysisRule,
  type AnalysisSignal,
  type InvestmentAnalysis,
  type RefreshJob,
  type SymbolRow,
  type Task,
  type TaskStatus,
  type TaskTag
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
  { key: 'invest-support', label: '投資支援', icon: BarChart3 },
  { key: 'household', label: '家計簿', icon: CreditCard },
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
  { period: 75, label: '75日移動平均線', shortLabel: '75日' },
  { period: 100, label: '100日移動平均線', shortLabel: '100日' },
  { period: 200, label: '200日移動平均線', shortLabel: '200日' }
]
const chartDrawingModes = [
  { value: 'none' as const, label: '通常操作', shortLabel: '通常' },
  { value: 'support' as const, label: 'サポートラインを描画', shortLabel: '支持' },
  { value: 'resistance' as const, label: 'レジスタンスラインを描画', shortLabel: '抵抗' }
]
const taskSortOptions = [
  { value: 'title' as const, label: '名前' },
  { value: 'status' as const, label: '進行度' },
  { value: 'due' as const, label: '期限' },
  { value: 'duration' as const, label: '継続期間' },
  { value: 'tag' as const, label: 'タグ' },
  { value: 'details' as const, label: '詳細' }
]
const taskTableColumns = [
  { value: 'title' as const, label: '名前', class: 'w-[18%]' },
  { value: 'status' as const, label: '進行度', class: 'w-28' },
  { value: 'due' as const, label: '期限', class: 'w-28' },
  { value: 'duration' as const, label: '継続期間', class: 'w-24 text-right' },
  { value: 'tag' as const, label: 'タグ', class: 'w-[18%]' },
  { value: 'details' as const, label: '詳細', class: '' }
]
const analysisCategoryColumns = [
  { value: 'side' as const, label: '区分', class: 'w-16', align: 'left' },
  { value: 'categoryA' as const, label: 'カテゴリA', class: 'w-44', align: 'left' },
  { value: 'categoryB' as const, label: '同時カテゴリB', class: 'w-44', align: 'left' },
  { value: 'relation' as const, label: '定義上の関係', class: '', align: 'left' },
  { value: 'ruleCount' as const, label: 'ルール数', class: 'w-24 text-right', align: 'right' },
  { value: 'current' as const, label: '現在', class: 'w-20 text-right', align: 'right' },
  { value: 'strength' as const, label: '強さ', class: 'w-24 text-right', align: 'right' },
  { value: 'signals' as const, label: '検証数', class: 'w-24 text-right', align: 'right' },
  { value: 'accuracy' as const, label: '正答率', class: 'w-24 text-right', align: 'right' },
  { value: 'expectedReturn' as const, label: '期待騰落率', class: 'w-28 text-right', align: 'right' },
  { value: 'interactionEffect' as const, label: 'A単独平均との差', class: 'w-32 text-right', align: 'right' }
]
const analysisRuleColumns = [
  { value: 'side' as const, label: '区分', class: 'w-16', align: 'left' },
  { value: 'name' as const, label: 'ルール', class: 'w-56', align: 'left' },
  { value: 'condition' as const, label: '条件', class: '', align: 'left' },
  { value: 'current' as const, label: '現在', class: 'w-20 text-right', align: 'right' },
  { value: 'strength' as const, label: '強さ', class: 'w-24 text-right', align: 'right' },
  { value: 'signals' as const, label: '検証数', class: 'w-24 text-right', align: 'right' },
  { value: 'accuracy' as const, label: '正答率', class: 'w-24 text-right', align: 'right' },
  { value: 'expectedReturn' as const, label: '期待騰落率', class: 'w-28 text-right', align: 'right' },
  { value: 'averageWidth' as const, label: '平均幅', class: 'w-28 text-right', align: 'right' }
]

type ChartDrawingMode = (typeof chartDrawingModes)[number]['value']
type TaskSort = (typeof taskSortOptions)[number]['value']
type SortDirection = 'asc' | 'desc'
type AnalysisSideFilter = 'すべて' | '買い' | '売り'
type AnalysisCategorySort = (typeof analysisCategoryColumns)[number]['value']
type AnalysisRuleSort = (typeof analysisRuleColumns)[number]['value']
type AnalysisCategoryCurrentSymbol = {
  symbol_id: number
  ticker: string
  name: string
  close: number
  signal_count: number
}
type ChartGuideLine = {
  id: string
  type: 'support' | 'resistance'
  startRatio: number
  endRatio: number
  startValue: number
  endValue: number
}

const activeTab = ref('invest')
const mobileOpen = ref(false)
const symbols = ref<SymbolRow[]>([])
const selectedId = ref<number | null>(null)
const history = ref<PricePoint[]>([])
const activeRange = ref('1y')
const chartMode = ref<(typeof chartModes)[number]['value']>('line')
const movingAveragePeriods = ref<number[]>([])
const chartDrawingMode = ref<ChartDrawingMode>('none')
const chartGuideLinesBySymbol = ref<Record<number, ChartGuideLine[]>>({})
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
const tasks = ref<Task[]>([])
const taskTags = ref<TaskTag[]>([])
const taskError = ref('')
const household = ref<HouseholdAnalysis | null>(null)
const householdError = ref('')
const householdMonth = ref('')
const householdImporting = ref(false)
const householdLoading = ref(false)
const householdFileInput = ref<HTMLInputElement | null>(null)
const analysis = ref<InvestmentAnalysis | null>(null)
const analysisError = ref('')
const analysisLoading = ref(false)
const analysisSideFilter = ref<AnalysisSideFilter>('すべて')
const analysisSignalFilter = ref('all')
const expandedAnalysisRuleKeys = ref<string[]>([])
const expandedAnalysisCategoryKeys = ref<string[]>([])
const expandedAnalysisCategorySignalKey = ref<string | null>(null)
const categoryBacktestOpen = ref(true)
const ruleBacktestOpen = ref(true)
const analysisCategorySort = ref<AnalysisCategorySort>('expectedReturn')
const analysisCategorySortDirection = ref<SortDirection>('desc')
const analysisRuleSort = ref<AnalysisRuleSort>('expectedReturn')
const analysisRuleSortDirection = ref<SortDirection>('desc')
const analysisLookbackYears = ref(5)
const analysisHorizonDays = ref(20)
const taskSort = ref<TaskSort>('due')
const taskSortDirection = ref<SortDirection>('asc')
const editingTaskId = ref<number | null>(null)
const taskTitle = ref('')
const taskStatus = ref<TaskStatus>('todo')
const taskDueDate = ref('')
const taskDurationDays = ref<number | null>(null)
const taskDetails = ref('')
const selectedTaskTagIds = ref<number[]>([])
const newTaskTagName = ref('')
const newTaskTagColor = ref('#7dd3fc')
let jobsTimer: number | undefined
let analysisTimer: number | undefined

const selectedSymbol = computed(() => symbols.value.find((symbol) => symbol.id === selectedId.value) ?? null)
const selectedChartGuideLines = computed(() => (selectedId.value ? chartGuideLinesBySymbol.value[selectedId.value] ?? [] : []))
const currentTab = computed(() => tabs.find((tab) => tab.key === activeTab.value))
const editingTask = computed(() => tasks.value.find((task) => task.id === editingTaskId.value) ?? null)
const taskSortMark = computed(() => (taskSortDirection.value === 'asc' ? '↑' : '↓'))
const analysisCategorySortMark = computed(() => (analysisCategorySortDirection.value === 'asc' ? '↑' : '↓'))
const analysisRuleSortMark = computed(() => (analysisRuleSortDirection.value === 'asc' ? '↑' : '↓'))
const symbolTags = computed(() => {
  const tags = Array.from(new Set(symbols.value.map((symbol) => symbol.tag || 'ウォッチリスト'))).sort((a, b) =>
    a.localeCompare(b, 'ja')
  )
  return ['すべて', ...tags]
})
const visibleSymbols = computed(() =>
  activeSymbolTag.value === 'すべて' ? symbols.value : symbols.value.filter((symbol) => symbol.tag === activeSymbolTag.value)
)
const visibleTasks = computed(() => tasks.value.filter((task) => !task.tags.some((tag) => tag.hidden)))
const sortedVisibleTasks = computed(() => [...visibleTasks.value].sort(compareTasks))
const activeTasks = computed(() => sortedVisibleTasks.value.filter((task) => task.status !== 'done'))
const completedTasks = computed(() =>
  sortedVisibleTasks.value
    .filter((task) => task.status === 'done')
    .sort((a, b) => (b.completed_at ?? '').localeCompare(a.completed_at ?? '') || b.id - a.id)
)
const householdMonthOptions = computed(() => household.value?.monthly.map((row) => row.month) ?? [])
const householdTransactions = computed(() => household.value?.transactions ?? [])
const householdCategories = computed(() => household.value?.categories ?? [])
const householdMonthlyDesc = computed(() => household.value?.monthly ?? [])
const householdCategoryOptions = computed(() => {
  const defaults = ['食費', '日用品', '娯楽', 'サブスク', '交通', '通信', '住居', '投資・貯蓄', '手数料', 'その他', '収入']
  const fromData = householdTransactions.value.map((transaction) => transaction.category)
  return Array.from(new Set([...defaults, ...fromData])).sort((a, b) => a.localeCompare(b, 'ja'))
})
const householdTopCategory = computed(() => householdCategories.value[0] ?? null)
const householdSelectedMonthLabel = computed(() => householdMonth.value || '全期間')
const householdAssetPoints = computed(() => household.value?.asset_points ?? [])
const householdAssetChart = computed(() => buildHouseholdAssetChart())
const analysisSideFilters: AnalysisSideFilter[] = ['すべて', '買い', '売り']
const analysisSignalRuleOptions = computed(() =>
  Array.from(new Set((analysis.value?.signals ?? []).map((signal) => signal.rule_name))).sort((a, b) =>
    a.localeCompare(b, 'ja')
  )
)
const analysisSignalSideOptions = computed(() =>
  Array.from(new Set((analysis.value?.signals ?? []).map((signal) => signal.side))).sort((a, b) => a.localeCompare(b, 'ja'))
)
const analysisSignalSymbolOptions = computed(() => {
  const symbolsById = new Map<number, { id: number; label: string; sortKey: string }>()
  for (const signal of analysis.value?.signals ?? []) {
    symbolsById.set(signal.symbol_id, {
      id: signal.symbol_id,
      label: `${signal.ticker} / ${signal.name}`,
      sortKey: `${signal.ticker} ${signal.name}`
    })
  }
  return [...symbolsById.values()].sort((a, b) => a.sortKey.localeCompare(b.sortKey, 'ja'))
})
const analysisSignals = computed<AnalysisSignal[]>(() =>
  filteredAnalysisSignals().sort(
    (a, b) => a.rule_name.localeCompare(b.rule_name, 'ja') || a.side.localeCompare(b.side, 'ja') || a.ticker.localeCompare(b.ticker)
  )
)
const filteredAnalysisRules = computed<AnalysisRule[]>(() => {
  const rules = analysis.value?.rules ?? []
  const filtered = analysisSideFilter.value === 'すべて' ? rules : rules.filter((rule) => rule.side === analysisSideFilter.value)
  return [...filtered].sort(compareAnalysisRules)
})
const filteredAnalysisCategories = computed<AnalysisCategory[]>(() => {
  const categories = analysis.value?.categories ?? []
  const filtered =
    analysisSideFilter.value === 'すべて' ? categories : categories.filter((category) => category.side === analysisSideFilter.value)
  return [...filtered].sort(compareAnalysisCategories)
})
const standardizedRuleStrengthByName = computed(() => {
  const rules = analysis.value?.rules ?? []
  const result = new Map<string, number>()
  for (const side of ['買い', '売り']) {
    const sideRules = rules.filter((rule) => rule.side === side)
    const rawValues = sideRules.map((rule) => ruleRawSignalStrength(rule))
    const minValue = Math.min(...rawValues)
    const maxValue = Math.max(...rawValues)
    for (const rule of sideRules) {
      const raw = ruleRawSignalStrength(rule)
      result.set(rule.name, maxValue > minValue ? ((raw - minValue) / (maxValue - minValue)) * 100 : 50)
    }
  }
  return result
})
const standardizedCategoryStrengthByKey = computed(() => {
  const categories = analysis.value?.categories ?? []
  const result = new Map<string, number>()
  for (const side of ['買い', '売り']) {
    const sideCategories = categories.filter((category) => category.side === side)
    const rawValues = sideCategories.map((category) => categoryRawSignalStrength(category))
    const minValue = Math.min(...rawValues)
    const maxValue = Math.max(...rawValues)
    for (const category of sideCategories) {
      const raw = categoryRawSignalStrength(category)
      result.set(analysisCategoryKey(category), maxValue > minValue ? ((raw - minValue) / (maxValue - minValue)) * 100 : 50)
    }
  }
  return result
})
const analysisAccuracyAverage = computed(() => {
  const values = filteredAnalysisRules.value
    .map((rule) => rule.backtest.accuracy_percent)
    .filter((value): value is number => value !== null)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
})
const analysisReturnAverage = computed(() => {
  const values = filteredAnalysisRules.value
    .map((rule) => rule.backtest.average_return_percent)
    .filter((value): value is number => value !== null)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
})
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

watch(activeTab, (tab) => {
  if (tab === 'invest-support' && analysis.value === null && !analysisLoading.value) {
    void loadInvestmentAnalysis()
  }
  if (tab === 'household' && household.value === null && !householdLoading.value) {
    void loadHousehold()
  }
})

watch([analysisSignalRuleOptions, analysisSignalSideOptions, analysisSignalSymbolOptions], () => {
  if (!isValidAnalysisSignalFilter(analysisSignalFilter.value)) {
    analysisSignalFilter.value = 'all'
  }
})

onMounted(async () => {
  await load()
  await loadTaskData()
  await loadJobs()
  jobsTimer = window.setInterval(loadJobs, 5000)
})

onUnmounted(() => {
  if (jobsTimer) window.clearInterval(jobsTimer)
  if (analysisTimer) window.clearInterval(analysisTimer)
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

async function loadTaskData() {
  try {
    taskError.value = ''
    const [loadedTags, loadedTasks] = await Promise.all([listTaskTags(), listTasks()])
    taskTags.value = loadedTags
    tasks.value = loadedTasks
    if (editingTaskId.value && !tasks.value.some((task) => task.id === editingTaskId.value)) {
      resetTaskForm()
    }
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タスクの読み込みに失敗しました'
  }
}

async function loadHousehold() {
  householdLoading.value = true
  try {
    householdError.value = ''
    household.value = await getHouseholdAnalysis(householdMonth.value || undefined)
    if (!householdMonth.value && household.value.monthly[0]?.month) {
      householdMonth.value = household.value.monthly[0].month
      household.value = await getHouseholdAnalysis(householdMonth.value)
    }
  } catch (err) {
    householdError.value = err instanceof Error ? err.message : '家計簿データの読み込みに失敗しました'
  } finally {
    householdLoading.value = false
  }
}

async function importHouseholdSampleData() {
  householdImporting.value = true
  try {
    householdError.value = ''
    const result = await importHouseholdSamples()
    await loadHousehold()
    householdError.value = `${result.imported}件を取り込み、${result.skipped}件をスキップしました。${result.excluded}件を集計除外しました`
  } catch (err) {
    householdError.value = err instanceof Error ? err.message : 'サンプルCSVの取り込みに失敗しました'
  } finally {
    householdImporting.value = false
  }
}

async function uploadHouseholdCsv(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (files.length === 0) return
  householdImporting.value = true
  try {
    householdError.value = ''
    const result = await importHouseholdCsv(files)
    await loadHousehold()
    householdError.value = `${result.imported}件を取り込み、${result.skipped}件をスキップしました。${result.excluded}件を集計除外しました`
  } catch (err) {
    householdError.value = err instanceof Error ? err.message : 'CSVの取り込みに失敗しました'
  } finally {
    input.value = ''
    householdImporting.value = false
  }
}

async function setHouseholdMonth(month: string) {
  householdMonth.value = month
  await loadHousehold()
}

function buildHouseholdAssetChart() {
  const points = householdAssetPoints.value
  const width = 720
  const height = 220
  const left = 48
  const right = 16
  const top = 14
  const bottom = 36
  const chartWidth = width - left - right
  const chartHeight = height - top - bottom
  if (points.length === 0) {
    return {
      points: [] as Array<{ date: string; balance: number; x: number; y: number }>,
      linePath: '',
      areaPath: '',
      minBalance: 0,
      maxBalance: 0,
      firstDate: '',
      lastDate: ''
    }
  }
  const balances = points.map((point) => point.balance)
  const minBalance = Math.min(...balances)
  const maxBalance = Math.max(...balances)
  const span = Math.max(1, maxBalance - minBalance)
  const chartPoints = points.map((point, index) => {
    const x = left + (points.length === 1 ? chartWidth : (index / (points.length - 1)) * chartWidth)
    const y = top + ((maxBalance - point.balance) / span) * chartHeight
    return { ...point, x, y }
  })
  const linePath = chartPoints.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(' ')
  const areaPath =
    chartPoints.length > 0
      ? `${linePath} L ${chartPoints[chartPoints.length - 1].x.toFixed(2)} ${height - bottom} L ${left} ${height - bottom} Z`
      : ''
  return {
    points: chartPoints,
    linePath,
    areaPath,
    minBalance,
    maxBalance,
    firstDate: points[0]?.date ?? '',
    lastDate: points[points.length - 1]?.date ?? ''
  }
}

async function changeHouseholdCategory(transaction: HouseholdTransaction, category: string) {
  try {
    householdError.value = ''
    await updateHouseholdTransaction(transaction.id, { category })
    await loadHousehold()
  } catch (err) {
    householdError.value = err instanceof Error ? err.message : 'カテゴリ更新に失敗しました'
  }
}

async function toggleHouseholdExcluded(transaction: HouseholdTransaction) {
  try {
    householdError.value = ''
    await updateHouseholdTransaction(transaction.id, { excluded: !transaction.excluded })
    await loadHousehold()
  } catch (err) {
    householdError.value = err instanceof Error ? err.message : '除外設定に失敗しました'
  }
}

async function loadInvestmentAnalysis() {
  try {
    analysisError.value = ''
    analysis.value = await getInvestmentAnalysis()
    analysisLookbackYears.value = analysis.value.lookback_years
    analysisHorizonDays.value = analysis.value.horizon_days
    analysisLoading.value = analysis.value.status === 'running'
    updateAnalysisPolling()
  } catch (err) {
    analysisError.value = err instanceof Error ? err.message : '投資支援データの読み込みに失敗しました'
  }
}

async function retryInvestmentBacktest() {
  try {
    analysisError.value = ''
    analysisLoading.value = true
    analysis.value = await recalculateInvestmentAnalysis({
      horizonDays: analysisHorizonDays.value,
      lookbackYears: analysisLookbackYears.value
    })
    updateAnalysisPolling()
  } catch (err) {
    analysisLoading.value = false
    analysisError.value = err instanceof Error ? err.message : 'バックテスト再試行に失敗しました'
  }
}

function updateAnalysisPolling() {
  if (analysisTimer) {
    window.clearInterval(analysisTimer)
    analysisTimer = undefined
  }
  if (analysis.value?.status === 'running') {
    analysisTimer = window.setInterval(loadInvestmentAnalysis, 5000)
  }
}

function analysisRuleKey(rule: AnalysisRule) {
  return `${rule.side}:${rule.name}`
}

function analysisCategoryKey(category: AnalysisCategory) {
  return `${category.side}:${category.name}`
}

function isAnalysisRuleExpanded(rule: AnalysisRule) {
  return expandedAnalysisRuleKeys.value.includes(analysisRuleKey(rule))
}

function toggleAnalysisRuleDetail(rule: AnalysisRule) {
  const key = analysisRuleKey(rule)
  expandedAnalysisRuleKeys.value = isAnalysisRuleExpanded(rule)
    ? expandedAnalysisRuleKeys.value.filter((value) => value !== key)
    : [...expandedAnalysisRuleKeys.value, key]
}

function isAnalysisCategoryExpanded(category: AnalysisCategory) {
  return expandedAnalysisCategoryKeys.value.includes(analysisCategoryKey(category))
}

function toggleAnalysisCategoryDetail(category: AnalysisCategory) {
  const key = analysisCategoryKey(category)
  expandedAnalysisCategoryKeys.value = isAnalysisCategoryExpanded(category)
    ? expandedAnalysisCategoryKeys.value.filter((value) => value !== key)
    : [...expandedAnalysisCategoryKeys.value, key]
}

function isAnalysisCategorySignalsExpanded(category: AnalysisCategory) {
  return expandedAnalysisCategorySignalKey.value === analysisCategoryKey(category)
}

function toggleAnalysisCategorySignals(category: AnalysisCategory) {
  const key = analysisCategoryKey(category)
  expandedAnalysisCategorySignalKey.value = expandedAnalysisCategorySignalKey.value === key ? null : key
}

function selectSignalRuleFilter(ruleName: string) {
  analysisSignalFilter.value = `rule:${ruleName}`
}

function selectSignalSymbolFilter(symbolId: number) {
  analysisSignalFilter.value = `symbol:${symbolId}`
}

function setAnalysisCategorySort(sort: AnalysisCategorySort) {
  if (analysisCategorySort.value === sort) {
    analysisCategorySortDirection.value = analysisCategorySortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  analysisCategorySort.value = sort
  analysisCategorySortDirection.value = isAnalysisTextCategorySort(sort) ? 'asc' : 'desc'
}

function setAnalysisRuleSort(sort: AnalysisRuleSort) {
  if (analysisRuleSort.value === sort) {
    analysisRuleSortDirection.value = analysisRuleSortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  analysisRuleSort.value = sort
  analysisRuleSortDirection.value = isAnalysisTextRuleSort(sort) ? 'asc' : 'desc'
}

function isAnalysisTextCategorySort(sort: AnalysisCategorySort) {
  return ['side', 'categoryA', 'categoryB', 'relation'].includes(sort)
}

function isAnalysisTextRuleSort(sort: AnalysisRuleSort) {
  return ['side', 'name', 'condition'].includes(sort)
}

function compareAnalysisCategories(a: AnalysisCategory, b: AnalysisCategory) {
  const sort = analysisCategorySort.value
  const direction = analysisCategorySortDirection.value === 'asc' ? 1 : -1
  const result =
    isAnalysisTextCategorySort(sort)
      ? compareText(analysisCategoryTextValue(a, sort), analysisCategoryTextValue(b, sort))
      : compareNumber(analysisCategoryNumberValue(a, sort), analysisCategoryNumberValue(b, sort))
  return result * direction || compareText(a.side, b.side) || compareText(a.name, b.name)
}

function compareAnalysisRules(a: AnalysisRule, b: AnalysisRule) {
  const sort = analysisRuleSort.value
  const direction = analysisRuleSortDirection.value === 'asc' ? 1 : -1
  const result =
    isAnalysisTextRuleSort(sort)
      ? compareText(analysisRuleTextValue(a, sort), analysisRuleTextValue(b, sort))
      : compareNumber(analysisRuleNumberValue(a, sort), analysisRuleNumberValue(b, sort))
  return result * direction || compareText(a.side, b.side) || compareText(a.name, b.name)
}

function analysisCategoryTextValue(category: AnalysisCategory, sort: AnalysisCategorySort) {
  if (sort === 'side') return category.side
  if (sort === 'categoryA') return category.category_a ?? category.name
  if (sort === 'categoryB') return category.category_b ?? ''
  if (sort === 'relation') return category.relation ?? ''
  return ''
}

function analysisCategoryNumberValue(category: AnalysisCategory, sort: AnalysisCategorySort) {
  if (sort === 'ruleCount') return category.rule_count
  if (sort === 'current') return category.current_signal_count
  if (sort === 'strength') return categorySignalStrength(category)
  if (sort === 'signals') return category.backtest.signals
  if (sort === 'accuracy') return category.backtest.accuracy_percent
  if (sort === 'expectedReturn') return category.backtest.average_return_percent
  if (sort === 'interactionEffect') return category.interaction_effect_return_percent
  return null
}

function analysisRuleTextValue(rule: AnalysisRule, sort: AnalysisRuleSort) {
  if (sort === 'side') return rule.side
  if (sort === 'name') return rule.name
  if (sort === 'condition') return `${rule.condition} ${rule.description}`
  return ''
}

function analysisRuleNumberValue(rule: AnalysisRule, sort: AnalysisRuleSort) {
  if (sort === 'current') return rule.current_signal_count
  if (sort === 'strength') return ruleSignalStrength(rule)
  if (sort === 'signals') return rule.backtest.signals
  if (sort === 'accuracy') return rule.backtest.accuracy_percent
  if (sort === 'expectedReturn') return rule.backtest.average_return_percent
  if (sort === 'averageWidth') return rule.backtest.average_abs_return_percent
  return null
}

function compareText(a: string, b: string) {
  return a.localeCompare(b, 'ja')
}

function compareNumber(a: number | null, b: number | null) {
  const normalizedA = a ?? Number.NEGATIVE_INFINITY
  const normalizedB = b ?? Number.NEGATIVE_INFINITY
  return normalizedA - normalizedB
}

function analysisCategoryCurrentSymbols(category: AnalysisCategory): AnalysisCategoryCurrentSymbol[] {
  const categoryA = category.category_a ?? category.name
  const categoryB = category.category_b
  const symbolsById = new Map<number, AnalysisCategoryCurrentSymbol>()
  const signalsBySymbol = new Map<number, AnalysisSignal[]>()
  for (const signal of analysis.value?.signals ?? []) {
    const existing = signalsBySymbol.get(signal.symbol_id) ?? []
    existing.push(signal)
    signalsBySymbol.set(signal.symbol_id, existing)
  }
  for (const symbolSignals of signalsBySymbol.values()) {
    const hasCategoryA = symbolSignals.some((signal) => signal.side === category.side && signal.primary_category === categoryA)
    if (!hasCategoryA) continue
    if (categoryB && !symbolSignals.some((signal) => signal.primary_category === categoryB)) continue
    const first = symbolSignals[0]
    symbolsById.set(first.symbol_id, {
      symbol_id: first.symbol_id,
      ticker: first.ticker,
      name: first.name,
      close: first.close,
      signal_count: symbolSignals.length
    })
  }
  return [...symbolsById.values()].sort((a, b) => a.ticker.localeCompare(b.ticker))
}

function openCategoryCurrentSymbol(symbolId: number) {
  selectSignalSymbolFilter(symbolId)
  document.getElementById('current-signals-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function ruleSignalStrength(rule: AnalysisRule) {
  return standardizedRuleStrengthByName.value.get(rule.name) ?? 0
}

function categorySignalStrength(category: AnalysisCategory) {
  return standardizedCategoryStrengthByKey.value.get(analysisCategoryKey(category)) ?? 0
}

function ruleRawSignalStrength(rule: AnalysisRule) {
  if (isWidthExtractionRule(rule)) {
    return Math.max(0, rule.backtest.average_abs_return_percent ?? 0)
  }
  return Math.max(0, rule.backtest.average_return_percent ?? 0)
}

function categoryRawSignalStrength(category: AnalysisCategory) {
  const categoryName = category.category_a ?? category.name
  const relatedRules = (analysis.value?.rules ?? []).filter(
    (rule) => rule.side === category.side && rule.primary_category === categoryName
  )
  if (relatedRules.some(isWidthExtractionRule)) {
    return Math.max(0, category.backtest.average_abs_return_percent ?? 0)
  }
  return Math.max(0, category.backtest.average_return_percent ?? 0)
}

function isWidthExtractionRule(rule: AnalysisRule) {
  const text = `${rule.name} ${rule.condition} ${rule.description}`
  return /幅|ボラ|ATR|騰落率|値幅|急伸|大きく伸び|リターン重視|高騰落率/.test(text)
}

function signalRuleStrength(signal: AnalysisSignal) {
  return standardizedRuleStrengthByName.value.get(signal.rule_name) ?? 0
}

function signalCategoryAdjustedStrength(signal: AnalysisSignal, symbolSignals: AnalysisSignal[]) {
  const categoryName = signal.primary_category ?? '未分類'
  const baseStrength = signalRuleStrength(signal)
  const interactions = analysis.value?.category_interactions?.[categoryName] ?? {}
  const sameSideCategories = new Set(
    symbolSignals
      .filter((other) => other !== signal && other.side === signal.side)
      .map((other) => other.primary_category ?? '未分類')
  )
  const oppositeSideCategories = new Set(
    symbolSignals
      .filter((other) => other !== signal && other.side !== signal.side)
      .map((other) => other.primary_category ?? '未分類')
  )
  const sameSideFactor = [...sameSideCategories].reduce((sum, category) => sum + (interactions[category] ?? 0), 0)
  const oppositeSideFactor = [...oppositeSideCategories].reduce((sum, category) => sum - Math.abs(interactions[category] ?? 0), 0)
  return Math.max(0, baseStrength * Math.max(0.2, 1 + sameSideFactor + oppositeSideFactor))
}

function symbolSignalStrength(symbolId: number) {
  const signals = (analysis.value?.signals ?? []).filter((signal) => signal.symbol_id === symbolId)
  const buyStrength = signals
    .filter((signal) => signal.side === '買い')
    .reduce((sum, signal) => sum + signalCategoryAdjustedStrength(signal, signals), 0)
  const sellStrength = signals
    .filter((signal) => signal.side === '売り')
    .reduce((sum, signal) => sum + signalCategoryAdjustedStrength(signal, signals), 0)
  const total = buyStrength + sellStrength
  return {
    buyStrength,
    sellStrength,
    buyPercent: total > 0 ? (buyStrength / total) * 100 : 0,
    sellPercent: total > 0 ? (sellStrength / total) * 100 : 0
  }
}

function filteredAnalysisSignals() {
  const signals = [...(analysis.value?.signals ?? [])]
  const [kind, ...rest] = analysisSignalFilter.value.split(':')
  const value = rest.join(':')
  if (kind === 'rule') return signals.filter((signal) => signal.rule_name === value)
  if (kind === 'side') return signals.filter((signal) => signal.side === value)
  if (kind === 'symbol') return signals.filter((signal) => signal.symbol_id === Number(value))
  return signals
}

function isValidAnalysisSignalFilter(value: string) {
  const [kind, ...rest] = value.split(':')
  const target = rest.join(':')
  if (value === 'all') return true
  if (kind === 'rule') return analysisSignalRuleOptions.value.includes(target)
  if (kind === 'side') return analysisSignalSideOptions.value.includes(target)
  if (kind === 'symbol') return analysisSignalSymbolOptions.value.some((symbol) => symbol.id === Number(target))
  return false
}

async function openSignalTicker(symbolId: number) {
  activeTab.value = 'invest'
  selectedId.value = symbolId
  await loadHistory()
  await loadPurchases()
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

function setSelectedChartGuideLines(lines: ChartGuideLine[]) {
  if (!selectedId.value) return
  chartGuideLinesBySymbol.value = {
    ...chartGuideLinesBySymbol.value,
    [selectedId.value]: lines
  }
}

function clearSelectedChartGuideLines() {
  setSelectedChartGuideLines([])
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
  if (!selectedSymbol.value || !purchaseAmount.value) return
  if (isStockPurchaseInput.value && !purchaseQuantity.value) return
  try {
    error.value = ''
    const payload: { purchased_at: string; amount: number; quantity?: number; note?: string } = {
      purchased_at: purchaseDate.value,
      amount: isStockPurchaseInput.value ? purchaseAmount.value * purchaseQuantity.value! : purchaseAmount.value,
      note: purchaseNote.value || undefined
    }
    if (isStockPurchaseInput.value) {
      payload.quantity = purchaseQuantity.value!
    }
    await createPurchase(selectedSymbol.value.id, payload)
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

function taskPayload() {
  return {
    title: taskTitle.value.trim(),
    status: taskStatus.value,
    due_date: taskDueDate.value || null,
    duration_days: taskDurationDays.value === null || Number.isNaN(taskDurationDays.value) ? null : taskDurationDays.value,
    tag_ids: selectedTaskTagIds.value,
    details: taskDetails.value
  }
}

async function saveTask() {
  const payload = taskPayload()
  if (!payload.title) return
  try {
    taskError.value = ''
    if (editingTaskId.value) {
      await updateTask(editingTaskId.value, payload)
    } else {
      await createTask(payload)
    }
    resetTaskForm()
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タスクの保存に失敗しました'
  }
}

function editTask(task: Task) {
  editingTaskId.value = task.id
  taskTitle.value = task.title
  taskStatus.value = task.status
  taskDueDate.value = task.due_date ?? ''
  taskDurationDays.value = task.duration_days
  taskDetails.value = task.details
  selectedTaskTagIds.value = task.tags.map((tag) => tag.id)
}

function resetTaskForm() {
  editingTaskId.value = null
  taskTitle.value = ''
  taskStatus.value = 'todo'
  taskDueDate.value = ''
  taskDurationDays.value = null
  taskDetails.value = ''
  selectedTaskTagIds.value = []
}

async function changeTaskStatus(task: Task, status: TaskStatus) {
  try {
    taskError.value = ''
    await updateTask(task.id, { status })
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : '進行度の更新に失敗しました'
  }
}

async function removeTask(task: Task) {
  if (!window.confirm(`${task.title} を削除しますか？`)) return
  try {
    taskError.value = ''
    await deleteTask(task.id)
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タスクの削除に失敗しました'
  }
}

async function addTaskTag() {
  const name = newTaskTagName.value.trim()
  if (!name) return
  try {
    taskError.value = ''
    await createTaskTag({ name, color: newTaskTagColor.value })
    newTaskTagName.value = ''
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タグの追加に失敗しました'
  }
}

async function toggleTaskTagHidden(tag: TaskTag) {
  try {
    taskError.value = ''
    await updateTaskTag(tag.id, { hidden: !tag.hidden })
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タグの表示設定に失敗しました'
  }
}

async function removeTaskTag(tag: TaskTag) {
  if (!window.confirm(`${tag.name} を削除しますか？`)) return
  try {
    taskError.value = ''
    await deleteTaskTag(tag.id)
    selectedTaskTagIds.value = selectedTaskTagIds.value.filter((tagId) => tagId !== tag.id)
    await loadTaskData()
  } catch (err) {
    taskError.value = err instanceof Error ? err.message : 'タグの削除に失敗しました'
  }
}

async function removeSelected() {
  if (!selectedSymbol.value || !window.confirm(`${selectedSymbol.value.ticker} を削除しますか？`)) return
  await deleteSymbol(selectedSymbol.value.id)
  selectedId.value = null
  await load()
}

function compareTasks(a: Task, b: Task) {
  const direction = taskSortDirection.value === 'asc' ? 1 : -1
  let result = 0
  if (taskSort.value === 'title') {
    result = a.title.localeCompare(b.title, 'ja')
  } else if (taskSort.value === 'status') {
    result = statusSortKey(a.status) - statusSortKey(b.status)
  } else if (taskSort.value === 'tag') {
    result = taskTagSortKey(a).localeCompare(taskTagSortKey(b), 'ja')
  } else if (taskSort.value === 'duration') {
    result = taskDurationSortKey(a) - taskDurationSortKey(b)
  } else if (taskSort.value === 'details') {
    result = a.details.localeCompare(b.details, 'ja')
  } else {
    result = taskDueSortKey(a).localeCompare(taskDueSortKey(b))
  }
  return result * direction || a.title.localeCompare(b.title, 'ja') || a.id - b.id
}

function setTaskSort(sort: TaskSort) {
  if (taskSort.value === sort) {
    taskSortDirection.value = taskSortDirection.value === 'asc' ? 'desc' : 'asc'
    return
  }
  taskSort.value = sort
  taskSortDirection.value = 'asc'
}

function taskDueSortKey(task: Task) {
  return task.due_date || '9999-12-31'
}

function taskDurationSortKey(task: Task) {
  return task.duration_days ?? Number.MAX_SAFE_INTEGER
}

function taskTagSortKey(task: Task) {
  return task.tags.map((tag) => tag.name).sort((a, b) => a.localeCompare(b, 'ja'))[0] ?? '~~~~'
}

function statusSortKey(status: TaskStatus) {
  const order: Record<TaskStatus, number> = {
    todo: 0,
    doing: 1,
    done: 2
  }
  return order[status]
}

function taskStatusLabel(status: TaskStatus) {
  const labels: Record<TaskStatus, string> = {
    todo: '開始前',
    doing: '進行中',
    done: '完了'
  }
  return labels[status]
}

function taskStatusClass(status: TaskStatus) {
  if (status === 'done') return 'text-gain'
  if (status === 'doing') return 'text-accent'
  return 'text-neutral-500'
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
  const date = parseUtcDate(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ja-JP', {
    timeZone: 'Asia/Tokyo',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function formatDateTime(value: string | null) {
  if (!value) return 'N/A'
  const date = parseUtcDate(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('ja-JP', {
    timeZone: 'Asia/Tokyo',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function parseUtcDate(value: string) {
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(value)) {
    return new Date(value)
  }
  return new Date(`${value.replace(' ', 'T')}Z`)
}
</script>
