<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.stats.budget') }}</div>
          <div class="stat-value">{{ money(budgetAmount) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.stats.selectedTotal') }}</div>
          <div class="stat-value">{{ money(selectedTotal) }}</div>
        </div>
        <div :class="['stat-card', isOverBudget ? 'danger' : 'success']">
          <div class="stat-label">{{ t('restocking.stats.remaining') }}</div>
          <div class="stat-value">{{ money(remaining) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.stats.itemsSelected') }}</div>
          <div class="stat-value">{{ selectedRows.length }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetCard.title') }}</h3>
        </div>
        <div class="budget-control">
          <input
            v-model.number="budget"
            type="range"
            class="budget-slider"
            min="0"
            :max="sliderMax"
            :step="BUDGET_STEP"
            :aria-label="t('restocking.budgetCard.sliderLabel')"
          />
          <div class="budget-input-group">
            <input
              v-model.number="budget"
              type="number"
              class="budget-input"
              min="0"
              step="1"
              :aria-label="t('restocking.budgetCard.inputLabel')"
            />
            <span class="budget-unit">USD</span>
          </div>
        </div>
        <div class="budget-scale">
          <span>{{ money(0) }}</span>
          <span>{{ money(sliderMax) }}</span>
        </div>
        <p class="hint">{{ t('restocking.budgetCard.hint') }}</p>
      </div>

      <div v-if="successOrder" class="notice notice-success" role="status">
        {{ t('restocking.success', {
          id: successOrder.id,
          total: money(successOrder.total_cost),
          date: formatDate(successOrder.expected_delivery)
        }) }}
        <router-link to="/orders" class="notice-link">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="submitError" class="notice notice-error" role="alert">{{ submitError }}</div>

      <div class="card">
        <div class="card-header table-header">
          <h3 class="card-title">{{ t('restocking.tableTitle') }}</h3>
          <div class="actions">
            <button type="button" class="btn btn-secondary" @click="selectRecommended">
              {{ t('restocking.selectRecommended') }}
            </button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="!canPlaceOrder"
              @click="placeOrder"
            >
              {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
            </button>
          </div>
        </div>

        <div v-if="isOverBudget" class="notice notice-warning" role="alert">
          {{ t('restocking.overBudget', { amount: money(Math.abs(remaining)) }) }}
        </div>

        <div v-if="rows.length === 0" class="empty">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-check">{{ t('restocking.table.select') }}</th>
                <th>{{ t('restocking.table.item') }}</th>
                <th>{{ t('restocking.table.category') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.stockOnHand') }}</th>
                <th>{{ t('restocking.table.forecastedDemand') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.sku" :class="{ 'row-ordered': row.already_ordered }">
                <td class="col-check">
                  <input
                    type="checkbox"
                    :checked="isSelected(row)"
                    :disabled="row.already_ordered"
                    :aria-label="row.name"
                    @change="toggleRow(row, $event.target.checked)"
                  />
                </td>
                <td>
                  <div class="item-name"><strong>{{ translateProductName(row.name) }}</strong></div>
                  <div class="item-sku">{{ row.sku }}</div>
                  <span v-if="row.already_ordered" class="badge info">{{ t('restocking.badges.ordered') }}</span>
                  <span v-else-if="recommendedSkus.has(row.sku)" class="badge success">
                    {{ t('restocking.badges.recommended') }}
                  </span>
                </td>
                <td>{{ translateCategory(row.category) }}</td>
                <td>
                  <span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span>
                </td>
                <td>{{ row.stock_on_hand }}</td>
                <td>{{ row.forecasted_demand }}</td>
                <td>
                  <input
                    type="number"
                    class="qty-input"
                    min="1"
                    step="1"
                    :value="getQuantity(row)"
                    :disabled="row.already_ordered"
                    :aria-label="t('restocking.table.quantity')"
                    @input="setQuantity(row, $event.target.value)"
                    @blur="$event.target.value = getQuantity(row)"
                  />
                </td>
                <td>{{ money(row.unit_cost) }}</td>
                <td><strong>{{ money(getQuantity(row) * row.unit_cost) }}</strong></td>
                <td>{{ t('restocking.days', { days: row.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrencyWithDecimals } from '../utils/currency'

// Budget slider granularity (USD)
const BUDGET_STEP = 500

// Convert to integer cents so float sums (e.g. 0.1 + 0.2) never flip budget comparisons
const toCents = (amount) => Math.round(amount * 100)

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const recommendations = ref([])

    // Budget is always USD internally; slider and number input share this ref
    const budget = ref(0)
    // Per-sku user state: selection flags and edited quantities
    const selection = ref({})
    const quantities = ref({})

    const submitting = ref(false)
    const submitError = ref(null)
    const successOrder = ref(null)

    // Unit costs have cents (e.g. $12.50), so show 2 decimals in USD (JPY is always whole yen)
    const money = (amount) => formatCurrencyWithDecimals(amount, currentCurrency.value, 2)

    const translateCategory = (category) => {
      const map = {
        'Circuit Boards': 'categories.circuitBoards',
        'Sensors': 'categories.sensors',
        'Actuators': 'categories.actuators',
        'Controllers': 'categories.controllers',
        'Power Supplies': 'categories.powerSupplies',
        'Mechanical Components': 'categories.mechanicalComponents'
      }
      return map[category] ? t(map[category]) : category
    }

    // Validate the date before formatting; fall back to the raw string
    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString || ''
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    // Most urgent first
    const rows = computed(() =>
      [...recommendations.value].sort((a, b) => a.urgency_rank - b.urgency_rank)
    )

    // Guard against an empty/invalid number input
    const budgetAmount = computed(() => {
      const value = Number(budget.value)
      return Number.isFinite(value) && value >= 0 ? value : 0
    })

    // Slider max: cost of everything not yet ordered, rounded UP to the step (min one step)
    const sliderMax = computed(() => {
      const total = rows.value
        .filter(row => !row.already_ordered)
        .reduce((sum, row) => sum + row.line_cost, 0)
      return Math.max(BUDGET_STEP, Math.ceil(total / BUDGET_STEP) * BUDGET_STEP)
    })

    const getQuantity = (row) => {
      const q = quantities.value[row.sku]
      return Number.isInteger(q) && q >= 1 ? q : Math.max(row.suggested_quantity, 1)
    }

    // Accept only positive integers; ignore partial/invalid typing (blur restores the display)
    const setQuantity = (row, raw) => {
      const q = Math.floor(Number(raw))
      if (Number.isFinite(q) && q >= 1) {
        quantities.value = { ...quantities.value, [row.sku]: q }
      }
    }

    // Ordered rows can never count as selected, whatever the stored flag says
    const isSelected = (row) => !row.already_ordered && !!selection.value[row.sku]

    const toggleRow = (row, checked) => {
      if (row.already_ordered) return
      selection.value = { ...selection.value, [row.sku]: checked }
    }

    const selectedRows = computed(() => rows.value.filter(isSelected))

    const selectedTotal = computed(() => {
      const cents = selectedRows.value.reduce(
        (sum, row) => sum + toCents(getQuantity(row) * row.unit_cost), 0
      )
      return cents / 100
    })

    const remaining = computed(() => (toCents(budgetAmount.value) - toCents(selectedTotal.value)) / 100)
    const isOverBudget = computed(() => toCents(selectedTotal.value) > toCents(budgetAmount.value))

    // Greedy fill by urgency: add a row when its cost at the SUGGESTED quantity still fits
    // in what is left; rows that do not fit are skipped and later (cheaper) rows may still fit.
    // Depends only on budget and data, never on the user's current selection or edited quantities.
    const recommendedSkus = computed(() => {
      let left = toCents(budgetAmount.value)
      const picked = new Set()
      for (const row of rows.value) {
        if (row.already_ordered || row.suggested_quantity <= 0) continue
        const cost = toCents(row.suggested_quantity * row.unit_cost)
        if (cost <= left) {
          picked.add(row.sku)
          left -= cost
        }
      }
      return picked
    })

    // Apply the recommended fill to the selection and reset those quantities to suggested
    const selectRecommended = () => {
      const nextSelection = {}
      const nextQuantities = { ...quantities.value }
      for (const row of rows.value) {
        if (recommendedSkus.value.has(row.sku)) {
          nextSelection[row.sku] = true
          nextQuantities[row.sku] = row.suggested_quantity
        }
      }
      selection.value = nextSelection
      quantities.value = nextQuantities
    }

    const canPlaceOrder = computed(
      () => selectedRows.value.length > 0 && !isOverBudget.value && !submitting.value
    )

    const loadRecommendations = async () => {
      recommendations.value = await api.getRestockRecommendations()
    }

    const placeOrder = async () => {
      if (!canPlaceOrder.value) return
      submitting.value = true
      submitError.value = null
      successOrder.value = null
      try {
        const order = await api.createRestockOrder({
          budget: budgetAmount.value,
          items: selectedRows.value.map(row => ({ sku: row.sku, quantity: getQuantity(row) }))
        })
        successOrder.value = order
        selection.value = {}
        quantities.value = {}
        // Refresh so newly ordered items show as ordered; keep the confirmation visible
        await loadRecommendations()
      } catch (err) {
        submitError.value = err.response?.data?.detail || t('restocking.submitFailed')
        console.error('Place order error:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(async () => {
      try {
        await loadRecommendations()
        // Default budget: half of the slider max, snapped to the step
        budget.value = Math.round((sliderMax.value * 0.5) / BUDGET_STEP) * BUDGET_STEP
        // One-time initial fill; later budget changes only move the badges
        selectRecommended()
      } catch (err) {
        error.value = t('restocking.loadFailed', { message: err.message })
        console.error('Load error:', err)
      } finally {
        loading.value = false
      }
    })

    return {
      t,
      BUDGET_STEP,
      loading,
      error,
      rows,
      budget,
      budgetAmount,
      sliderMax,
      selectedRows,
      selectedTotal,
      remaining,
      isOverBudget,
      recommendedSkus,
      canPlaceOrder,
      submitting,
      submitError,
      successOrder,
      money,
      formatDate,
      translateCategory,
      translateProductName,
      getQuantity,
      setQuantity,
      isSelected,
      toggleRow,
      selectRecommended,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-control {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem 1.5rem 0;
}

.budget-slider {
  flex: 1;
  accent-color: #0f172a;
}

.budget-input-group {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.budget-input,
.qty-input {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 0.375rem 0.5rem;
  color: #0f172a;
  background: white;
  font-size: 0.875rem;
}

.budget-input {
  width: 8rem;
}

.qty-input {
  width: 5rem;
}

.qty-input:disabled {
  background: #f1f5f9;
  color: #64748b;
}

.budget-unit {
  font-size: 0.813rem;
  color: #64748b;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  padding: 0.25rem 1.5rem 0;
  font-size: 0.75rem;
  color: #64748b;
}

.hint {
  padding: 0.5rem 1.5rem 1rem;
  margin: 0;
  font-size: 0.813rem;
  color: #64748b;
}

.table-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.actions {
  display: flex;
  gap: 0.75rem;
}

.btn {
  border-radius: 6px;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid #0f172a;
}

.btn-primary {
  background: #0f172a;
  color: white;
}

.btn-secondary {
  background: white;
  color: #0f172a;
  border-color: #e2e8f0;
}

.btn-secondary:hover {
  background: #f8fafc;
}

.btn:disabled {
  background: #e2e8f0;
  color: #94a3b8;
  border-color: #e2e8f0;
  cursor: not-allowed;
}

.notice {
  border-radius: 8px;
  padding: 0.75rem 1rem;
  margin-bottom: 1.5rem;
  font-size: 0.875rem;
  border: 1px solid;
}

.card .notice {
  margin: 0 1.5rem 1rem;
}

.notice-success {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.notice-warning {
  background: #fffbeb;
  border-color: #fde68a;
  color: #92400e;
}

.notice-error {
  background: #fef2f2;
  border-color: #fecaca;
  color: #991b1b;
}

.notice-link {
  margin-left: 0.5rem;
  font-weight: 600;
  color: inherit;
  text-decoration: underline;
}

.empty {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.col-check {
  width: 3.5rem;
  text-align: center;
}

.item-sku {
  font-size: 0.75rem;
  color: #64748b;
  margin-bottom: 0.25rem;
}

.row-ordered {
  color: #94a3b8;
}
</style>
