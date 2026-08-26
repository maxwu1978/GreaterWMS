<template>
  <div
    ref="fullscreenTarget"
    class="operations-board-shell"
    :class="{ 'operations-board-shell--fullscreen': isFullscreen }"
    :style="{ '--board-scale': zoomPercent / 100 }"
  >
    <div class="operations-board__surface">
      <q-card class="operations-board shadow-11">
        <q-card-section class="operations-board__header row items-center q-px-md q-py-sm">
          <div class="operations-board__title">
            {{ label('operations_board.title', 'Warehouse Operations') }}
          </div>
          <q-space />
          <div v-if="viewerLabel" class="operations-board__viewer">{{ viewerLabel }}</div>
          <div class="operations-board__live">LIVE</div>
          <q-btn flat round dense color="white" icon="remove" :aria-label="label('operations_board.zoom_out', 'Zoom out')" @click="adjustZoom(-10)" />
          <button type="button" class="operations-board__zoom-value" :aria-label="label('operations_board.zoom_reset', 'Reset zoom')" @click="resetZoom">
            {{ zoomPercent }}%
          </button>
          <q-btn flat round dense color="white" icon="add" :aria-label="label('operations_board.zoom_in', 'Zoom in')" @click="adjustZoom(10)" />
          <q-btn flat round dense color="white" icon="refresh" :loading="loading" :aria-label="label('operations_board.refresh', 'Refresh')" @click="getList()" />
          <q-btn
            flat
            round
            dense
            color="white"
            :icon="isFullscreen ? 'fullscreen_exit' : 'fullscreen'"
            :aria-label="isFullscreen ? label('operations_board.exit_fullscreen', 'Exit fullscreen') : label('operations_board.fullscreen', 'Fullscreen')"
            @click="toggleFullscreen"
          />
        </q-card-section>

        <q-card-section class="operations-board__summary row items-center q-px-md q-py-xs">
          <q-tabs v-model="viewMode" dense align="left" active-color="primary" indicator-color="primary" class="operations-board__view-tabs">
            <q-tab name="active" :label="label('operations_board.active', 'Active')" />
            <q-tab name="history" :label="label('operations_board.history', 'History')" />
          </q-tabs>
          <q-space />
          <div class="operations-board__counts">
            <span class="operations-board__count">{{ countLabel('total', 'Total') }} {{ counts.total || 0 }}</span>
            <span v-if="viewMode === 'active'" class="operations-board__count operations-board__count--urgent">{{ countLabel('urgent', 'Urgent') }} {{ counts.urgent || 0 }}</span>
            <span v-if="viewMode === 'active'" class="operations-board__count operations-board__count--blocked">{{ countLabel('blocked', 'Blocked') }} {{ counts.blocked || 0 }}</span>
            <span v-if="viewMode === 'history'" class="operations-board__count">{{ countLabel('completed', 'Completed') }} {{ counts.completed || 0 }}</span>
          </div>
        </q-card-section>

        <q-card-section class="operations-board__controls row items-center q-pa-none">
          <q-tabs v-model="activeFilter" dense align="left" active-color="primary" indicator-color="primary" class="operations-board__filters">
            <q-tab v-for="filter in filters" :key="filter.key" :name="filter.key" :label="filter.label" />
          </q-tabs>
          <q-space />
          <q-btn v-if="hasMore" flat dense color="primary" class="q-mr-sm" :label="label('operations_board.load_more', 'Load More')" @click="loadMore" />
        </q-card-section>

        <greater-wms-operations-table
          :rows="filteredItems"
          :columns="columns"
          :row-class="rowClass"
          :loading="loading"
          :pagination.sync="pagination"
          :no-data-label="noDataLabel"
        >
          <template v-slot:body-cell-eta="props">
            <q-td :props="props">
              <div class="operations-board__eta-value">
                {{ props.row.eta ? compactDateTime(props.row.eta) : label('operations_board.eta_not_provided', 'Not Provided') }}
                <q-badge outline :color="etaStatusColor(props.row.eta_status)" class="operations-board__eta-status">
                  {{ etaStatusLabel(props.row.eta_status) }}
                </q-badge>
              </div>
              <div v-if="etaCountdown(props.row)" class="operations-board__eta-countdown">{{ etaCountdown(props.row) }}</div>
            </q-td>
          </template>
          <template v-slot:body-cell-customer="props">
            <q-td :props="props">
              <span :title="props.row.customer_full_name || props.row.customer">{{ compactOwnerName(props.row) }}</span>
            </q-td>
          </template>
          <template v-slot:body-cell-reference="props">
            <q-td :props="props">
              <button type="button" class="operations-board__reference" @click="showDetails(props.row)">
                <q-badge outline color="primary">{{ categoryLabel(props.row.category) }}</q-badge>
                <span :title="props.row.reference">{{ compactReference(props.row.reference) }}</span>
              </button>
            </q-td>
          </template>
          <template v-slot:body-cell-next_action="props">
            <q-td :props="props" class="operations-board__next-action-cell"><span class="operations-board__next-action">{{ props.row.next_action_label || props.row.next_action || operationLabel(props.row.operation) }}</span></q-td>
          </template>
          <template v-slot:body-cell-assigned_to="props">
            <q-td :props="props">{{ props.row.assignee_name || assignedRoleLabel(props.row.assigned_role) }}</q-td>
          </template>
          <template v-slot:body-cell-location="props">
            <q-td :props="props" class="operations-board__move-cell"><span class="operations-board__move" :title="props.row.location_summary || props.row.location">{{ compactLocation(props.row) }}</span></q-td>
          </template>
          <template v-slot:body-cell-quantity="props">
            <q-td :props="props" class="text-weight-medium text-right">{{ props.row.quantity_label || `${props.row.quantity} / ${props.row.total_quantity}` }}</q-td>
          </template>
          <template v-slot:body-cell-business_status="props">
            <q-td :props="props" class="operations-board__status-cell"><q-badge class="operations-board__status-badge" :color="businessStatusColor(props.row.business_status)">{{ businessStatusLabel(props.row.business_status) }}</q-badge></q-td>
          </template>
          <template v-slot:body-cell-action="props">
            <q-td :props="props">
              <q-btn flat dense color="primary" icon="open_in_new" :aria-label="label('operations_board.open', 'Open')" @click="showDetails(props.row)" />
            </q-td>
          </template>
        </greater-wms-operations-table>
      </q-card>
    </div>

    <q-dialog v-model="detailOpen" position="right">
      <q-card v-if="selectedItem" class="operations-board__detail">
        <q-card-section class="row items-center q-pb-sm">
          <div>
            <div class="text-subtitle1 text-weight-bold" :title="selectedItem.reference">{{ compactReference(selectedItem.reference) }}</div>
            <div class="text-caption text-grey-7" :title="selectedItem.customer_full_name || selectedItem.customer">{{ categoryLabel(selectedItem.category) }} · {{ compactOwnerName(selectedItem) }}</div>
          </div>
          <q-space />
          <q-btn flat round dense icon="close" @click="detailOpen = false" />
        </q-card-section>
        <q-separator />
        <q-card-section class="operations-board__detail-body">
          <div class="operations-board__detail-status row items-center q-mb-md">
            <q-badge :color="businessStatusColor(selectedItem.business_status)">{{ businessStatusLabel(selectedItem.business_status) }}</q-badge>
            <q-space />
            <span class="text-caption text-grey-7">{{ selectedItem.next_action_label || selectedItem.next_action || operationLabel(selectedItem.operation) }}</span>
          </div>

          <div class="operations-board__detail-grid">
            <div class="operations-board__detail-label">{{ label('operations_board.assigned_to', 'Assigned To') }}</div>
            <div>{{ selectedItem.assignee_name || assignedRoleLabel(selectedItem.assigned_role) }}</div>
            <div class="operations-board__detail-label">{{ label('operations_board.location', 'Location') }}</div>
            <div>{{ selectedItem.location_summary || selectedItem.location || '—' }}</div>
            <div class="operations-board__detail-label">{{ label('operations_board.quantity', 'Qty') }}</div>
            <div>{{ selectedItem.quantity_label || '—' }}</div>
            <div v-if="selectedItem.container_tracking" class="operations-board__detail-label">Container</div>
            <div v-if="selectedItem.container_tracking">{{ selectedItem.container_tracking }}</div>
            <div class="operations-board__detail-label">{{ label('operations_board.eta', 'ETA') }}</div>
            <div>{{ selectedItem.eta ? compactDateTime(selectedItem.eta) : label('operations_board.eta_not_provided', 'Not Provided') }}</div>
            <div v-if="selectedItem.linked_reference" class="operations-board__detail-label">Linked Ref</div>
            <div v-if="selectedItem.linked_reference">{{ selectedItem.linked_reference }}</div>
          </div>

          <div v-if="selectedItem.staging_bins && selectedItem.staging_bins.length" class="operations-board__detail-section">
            <div class="operations-board__detail-label">Staging</div>
            <div>{{ selectedItem.staging_bins.join(', ') }}</div>
          </div>

          <div v-if="acceptanceRows(selectedItem).length" class="operations-board__detail-section">
            <div class="operations-board__detail-label">Checks</div>
            <div v-for="row in acceptanceRows(selectedItem)" :key="row.label" class="operations-board__detail-line">
              <span>{{ row.label }}</span>
              <strong>{{ row.value }}</strong>
            </div>
          </div>

          <q-banner v-if="selectedItem.exception_summary || selectedItem.blocking_reason" dense rounded class="bg-red-1 text-negative q-mt-md">
            {{ selectedItem.exception_summary || selectedItem.blocking_reason }}
          </q-banner>

          <q-btn unelevated color="primary" class="full-width q-mt-lg" :label="label('operations_board.open_record', 'Open Record')" @click="openItem(selectedItem)" />
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'
import GreaterWmsOperationsTable from 'components/GreaterWmsOperationsTable.vue'

export default {
  name: 'OperationsBoard',
  components: { GreaterWmsOperationsTable },
  data () {
    return {
      viewMode: 'active',
      activeFilter: 'all',
      items: [],
      counts: {},
      viewer: { staff_name: '', staff_type: '', scope: '' },
      loading: false,
      refreshTimer: null,
      // The API paginates; the board should render every loaded row without a second hidden pager.
      pagination: { rowsPerPage: 0 },
      hasMore: false,
      detailOpen: false,
      selectedItem: null,
      isFullscreen: false,
      zoomPercent: 100
    }
  },
  computed: {
    filters () {
      if (this.viewMode === 'history') {
        return [
          { key: 'all', label: this.label('operations_board.all', 'All') },
          { key: 'completed', label: this.label('operations_board.completed', 'Completed') },
          { key: 'cancelled', label: this.label('operations_board.cancelled', 'Cancelled') }
        ]
      }
      return [
        { key: 'all', label: this.label('operations_board.all', 'All') },
        { key: 'urgent', label: this.label('operations_board.urgent', 'Urgent') },
        { key: 'now', label: this.label('operations_board.now', 'In Progress') },
        { key: 'next', label: this.label('operations_board.next', 'Pending') },
        { key: 'delayed', label: this.label('operations_board.delayed', 'Delayed') },
        { key: 'blocked', label: this.label('operations_board.blocked', 'Exception') }
      ]
    },
    noDataLabel () {
      return this.viewMode === 'history' ? this.label('operations_board.no_history', 'No processed work') : this.label('operations_board.no_work', 'No active warehouse work')
    },
    filteredItems () {
      if (this.activeFilter === 'all') return this.items
      if (this.activeFilter === 'urgent') return this.items.filter(item => ['DUE_SOON', 'OVERDUE'].includes(item.eta_status))
      return this.items.filter(item => item.lane === this.activeFilter)
    },
    viewerLabel () {
      if (!this.viewer.staff_type) return ''
      const name = this.viewer.staff_name || ''
      const role = this.viewer.staff_type
      return name ? `${name} · ${role}` : role
    },
    columns () {
      return [
        { name: 'eta', label: this.label('operations_board.eta_urgency', 'ETA / Urgency'), field: 'eta', align: 'left' },
        { name: 'customer', label: this.label('operations_board.customer', 'Customer'), field: 'customer', align: 'left' },
        { name: 'reference', label: this.label('operations_board.reference_type', 'Ref / Type'), field: 'reference', align: 'left' },
        { name: 'next_action', label: this.label('operations_board.next_action', 'Next Step'), field: 'next_action', align: 'left', style: 'min-width: 150px; width: 170px; max-width: 210px;', headerStyle: 'min-width: 150px; width: 170px; max-width: 210px;' },
        { name: 'assigned_to', label: this.label('operations_board.assigned_to', 'Assigned To'), field: 'assigned_to', align: 'left' },
        { name: 'location', label: this.label('operations_board.location', 'Move'), field: 'location_summary', align: 'left', style: 'min-width: 150px; width: 180px; max-width: 230px;', headerStyle: 'min-width: 150px; width: 180px; max-width: 230px;' },
        { name: 'quantity', label: this.label('operations_board.quantity_short', 'Qty'), field: 'quantity_label', align: 'right' },
        { name: 'business_status', label: this.label('operations_board.status', 'Status'), field: 'business_status', align: 'left', style: 'min-width: 140px; width: 160px; max-width: 200px;', headerStyle: 'min-width: 140px; width: 160px; max-width: 200px;' },
        { name: 'action', label: '', field: 'action', align: 'right' }
      ]
    }
  },
  watch: {
    viewMode () {
      this.activeFilter = 'all'
      this.getList()
    }
  },
  mounted () {
    this.loadZoom()
    document.addEventListener('fullscreenchange', this.syncFullscreen)
    document.addEventListener('webkitfullscreenchange', this.syncFullscreen)
    this.getList()
    this.refreshTimer = setInterval(() => this.getList(), 30000)
  },
  beforeDestroy () {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
    document.removeEventListener('fullscreenchange', this.syncFullscreen)
    document.removeEventListener('webkitfullscreenchange', this.syncFullscreen)
  },
  methods: {
    label (key, fallback) {
      const translated = this.$t(key)
      return translated === key ? fallback : translated
    },
    countLabel (key, fallback) {
      return this.label(`operations_board.${key}`, fallback)
    },
    getList ({ append = false } = {}) {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      const offset = append ? this.items.length : 0
      const path = `dashboard/operations/?view=${this.viewMode}&limit=200&offset=${offset}`
      getauth(path)
        .then(res => {
          this.items = append ? this.items.concat(res.items || []) : (res.items || [])
          this.viewer = res.viewer || { staff_name: '', staff_type: '', scope: '' }
          this.counts = res.counts || {}
          this.hasMore = Boolean(res.has_more)
        })
        .catch(() => {})
        .finally(() => {
          this.loading = false
        })
    },
    loadMore () {
      this.getList({ append: true })
    },
    showDetails (item) {
      this.selectedItem = item
      this.detailOpen = true
    },
    acceptanceRows (item) {
      const summary = item && item.acceptance_summary ? item.acceptance_summary : {}
      const rows = []
      if (summary.pack_list_status) rows.push({ label: 'Pack List', value: summary.pack_list_status })
      if (summary.qc_status) rows.push({ label: 'QC', value: summary.qc_status })
      if (summary.verification_mode) rows.push({ label: 'Check Mode', value: summary.verification_mode })
      if (summary.picking_mode) rows.push({ label: 'Pick Mode', value: summary.picking_mode })
      if (summary.expected_qty !== undefined) rows.push({ label: 'Expected', value: summary.expected_qty })
      if (summary.received_qty !== undefined) rows.push({ label: 'Received', value: summary.received_qty })
      if (summary.scanned_qty !== undefined) rows.push({ label: 'Scanned', value: summary.scanned_qty })
      if (summary.accepted_qty !== undefined) rows.push({ label: 'Accepted', value: summary.accepted_qty })
      if (summary.repair_qty) rows.push({ label: 'Repair / Hold', value: summary.repair_qty })
      if (summary.rejected_qty) rows.push({ label: 'Rejected', value: summary.rejected_qty })
      if (summary.open_exception_qty) rows.push({ label: 'Open Exceptions', value: summary.open_exception_qty })
      if (summary.requested_serials !== undefined) rows.push({ label: 'SN Requested', value: summary.requested_serials })
      if (summary.picked_serials !== undefined) rows.push({ label: 'SN Picked', value: summary.picked_serials })
      if (summary.shipped_serials !== undefined) rows.push({ label: 'SN Shipped', value: summary.shipped_serials })
      return rows
    },
    compactReference (value) {
      const code = String(value || '').trim()
      if (code.length <= 10) return code || '-'
      return code.slice(0, 4) + '...' + code.slice(-4)
    },
    compactOwnerName (row) {
      const shortName = String((row && row.customer_short_name) || '').trim()
      const fullName = String((row && (row.customer_full_name || row.customer)) || '').trim()
      const value = shortName || fullName
      if (!value) return '-'
      if (value.length <= 8) return value
      const firstWord = value.split(/\s+/)[0].replace(/[^a-zA-Z0-9&-]/g, '')
      return (firstWord || value).slice(0, 8).toUpperCase()
    },
    compactDateTime (value) {
      const normalized = String(value || '').replace('T', ' ')
      const match = normalized.match(/^(?:\d{4}-)?(\d{2})[-/](\d{2})\s+(\d{2}:\d{2})/)
      return match ? `${match[1]}/${match[2]} ${match[3]}` : normalized.slice(0, 16)
    },
    compactLocation (row) {
      if (!row) return '—'
      const source = this.compactArea(row.source_location)
      const target = this.compactArea(row.target_location || row.location)
      if (!source) return target || '—'
      return `${source} → ${target}`
    },
    compactArea (value) {
      const aliases = {
        Dock: 'DOCK',
        Stage: 'STG',
        'Stage / QC': 'STG/QC',
        Storage: 'STO',
        'Storage (bin pending)': 'STO?',
        Shipping: 'SHP',
        Customer: 'CUST'
      }
      return String(value || '')
        .split(',')
        .map(part => {
          const area = part.trim()
          if (!area) return ''
          if (aliases[area]) return aliases[area]
          const stageMatch = area.match(/^Stage[- ](left|right)(?:[- ]?)(.*)$/i)
          if (stageMatch) {
            const side = stageMatch[1].toUpperCase() === 'LEFT' ? 'L' : 'R'
            const suffix = stageMatch[2].trim()
            return suffix ? `${side}${suffix}` : side
          }
          return area
        })
        .filter(Boolean)
        .join(',')
    },
    operationLabel (operation) {
      const key = String(operation || '').toLowerCase()
      return this.label(`operations_board.${key}`, operation)
    },
    businessStatusLabel (status) {
      const key = String(status || '').toLowerCase()
      return this.label(`operations_board.status_${key}`, status || '-')
    },
    businessStatusColor (status) {
      const value = String(status || '').toUpperCase()
      const inboundColors = {
        PENDING_ARRIVAL: 'blue-2',
        READY_TO_UNLOAD: 'primary',
        UNLOADING: 'orange-3',
        RECEIVING_REVIEW: 'amber-3',
        QC_REVIEW_REQUIRED: 'negative',
        QC_PARTIAL_HOLD: 'amber-3',
        REPAIR_HOLD: 'orange-3',
        PACK_LIST_REVIEW: 'orange-3',
        READY_FOR_PUTAWAY: 'purple-3',
        READY_FOR_PUTAWAY_PARTIAL: 'purple-3',
        PUTAWAY_COMPLETE: 'positive'
      }
      if (inboundColors[value]) return inboundColors[value]
      if (value === 'COMPLETED' || value === 'MATCHED' || value === 'PUTAWAY_COMPLETE') return 'positive'
      if (value === 'CANCELLED' || value.includes('EXCEPTION') || value === 'DISPUTED' || value === 'REPAIR_HOLD') return 'negative'
      if (value === 'QC_PARTIAL_HOLD' || value === 'PACK_LIST_REVIEW') return 'warning'
      if (value.includes('PENDING') || value === 'PRE_ARRIVAL' || value === 'PENDING_ARRIVAL') return 'primary'
      if (['READY_TO_UNLOAD', 'UNLOADING', 'RECEIVING_REVIEW', 'READY_FOR_PUTAWAY', 'READY_FOR_PUTAWAY_PARTIAL'].includes(value)) return 'primary'
      return 'grey-7'
    },
    categoryLabel (category) {
      const key = String(category || '').toLowerCase()
      return this.label(`operations_board.${key}`, category)
    },
    locationLabel (location) {
      const key = String(location || '').toLowerCase()
      return this.label(`operations_board.${key}`, location)
    },
    assignedRoleLabel (role) {
      const labels = {
        DRIVER: this.label('operations_board.driver', 'Driver'),
        QC: this.label('operations_board.qc', 'QC'),
        WAREHOUSE: this.label('operations_board.warehouse', 'Warehouse'),
        LOGISTICS: this.label('operations_board.logistics', 'Logistics')
      }
      return labels[String(role || '').toUpperCase()] || role || ''
    },
    rowClass (row) {
      return `operations-board__row--${row.lane || 'default'}`
    },
    etaStatusLabel (status) {
      const key = String(status || 'NOT_PROVIDED').toLowerCase()
      return this.label(`operations_board.eta_${key}`, status || 'Not Provided')
    },
    etaStatusColor (status) {
      return {
        OVERDUE: 'negative',
        DUE_SOON: 'warning',
        ON_TIME: 'primary',
        ARRIVED: 'positive',
        COMPLETED: 'positive',
        CANCELLED: 'negative',
        NOT_PROVIDED: 'grey-7'
      }[String(status || 'NOT_PROVIDED').toUpperCase()] || 'grey-7'
    },
    etaCountdown (row) {
      const status = String(row.eta_status || '').toUpperCase()
      const minutes = Number(row.minutes_to_eta)
      if (!Number.isFinite(minutes) || !['DUE_SOON', 'ON_TIME', 'OVERDUE'].includes(status)) return ''
      const absoluteMinutes = Math.abs(minutes)
      const hours = Math.floor(absoluteMinutes / 60)
      const remainingMinutes = absoluteMinutes % 60
      const duration = hours ? `${hours}h ${remainingMinutes}m` : `${remainingMinutes}m`
      if (status === 'OVERDUE') return `${this.label('operations_board.eta_overdue_by', 'Overdue by')} ${duration}`
      return `${this.label('operations_board.eta_due_in', 'Due in')} ${duration}`
    },
    loadZoom () {
      const savedZoom = Number(window.localStorage.getItem('greaterwms.dashboard.zoom'))
      if (savedZoom >= 80 && savedZoom <= 140 && savedZoom % 10 === 0) this.zoomPercent = savedZoom
    },
    adjustZoom (delta) {
      this.zoomPercent = Math.min(140, Math.max(80, this.zoomPercent + delta))
      window.localStorage.setItem('greaterwms.dashboard.zoom', String(this.zoomPercent))
    },
    resetZoom () {
      this.zoomPercent = 100
      window.localStorage.setItem('greaterwms.dashboard.zoom', '100')
    },
    syncFullscreen () {
      this.isFullscreen = Boolean(document.fullscreenElement || document.webkitFullscreenElement)
    },
    toggleFullscreen () {
      const target = this.$refs.fullscreenTarget
      const activeElement = document.fullscreenElement || document.webkitFullscreenElement
      if (activeElement) {
        const exit = document.exitFullscreen || document.webkitExitFullscreen
        if (exit) exit.call(document)
        return
      }
      const request = target && (target.requestFullscreen || target.webkitRequestFullscreen)
      if (!request) {
        this.$q.notify({ message: this.label('operations_board.fullscreen_unavailable', 'Fullscreen is not supported by this browser'), color: 'negative', icon: 'fullscreen' })
        return
      }
      const result = request.call(target)
      if (result && result.catch) result.catch(() => {})
    },
    openItem (item) {
      if (!item || !item.action_route) return
      const query = { reference: item.reference }
      if (item.category === 'inbound') query.asn_code = item.reference
      if (item.category === 'receiving') query.receipt_no = item.reference
      if (item.category === 'outbound') query.dn_code = item.reference
      if (item.category === 'transport') query.transport_no = item.reference
      this.detailOpen = false
      this.$router.push({ name: item.action_route, query })
    }
  }
}
</script>

<style scoped>
.operations-board__eta-value { display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.operations-board__eta-status { font-size: 10px; line-height: 1.2; }
.operations-board__eta-countdown { margin-top: 2px; color: #6b7280; font-size: 11px; font-weight: 600; }
.operations-board__reference { display: inline-flex; align-items: center; gap: 6px; padding: 0; border: 0; background: transparent; color: #334155; cursor: pointer; font: inherit; text-align: left; }
.operations-board__reference:hover { color: #1976d2; }
.operations-board__next-action-cell,
.operations-board__move-cell,
.operations-board__status-cell { white-space: normal !important; vertical-align: middle; }
.operations-board__next-action,
.operations-board__move { display: block; white-space: normal; overflow-wrap: anywhere; line-height: 1.25; }
.operations-board__next-action { font-weight: 600; }
.operations-board__status-badge { max-width: 100%; white-space: normal; line-height: 1.25; text-align: center; }
.operations-board__detail { width: min(420px, 92vw); max-width: 420px; min-height: 100vh; }
.operations-board__detail-body { overflow-y: auto; }
.operations-board__detail-grid { display: grid; grid-template-columns: 120px 1fr; gap: 10px 14px; font-size: 13px; }
.operations-board__detail-label { color: #667085; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
.operations-board__detail-section { margin-top: 20px; padding-top: 14px; border-top: 1px solid #eaecf0; }
.operations-board__detail-line { display: flex; justify-content: space-between; gap: 12px; padding: 5px 0; font-size: 13px; }
</style>
