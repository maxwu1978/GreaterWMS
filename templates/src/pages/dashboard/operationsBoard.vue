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
          <div v-if="viewerLabel" class="operations-board__viewer">
            {{ viewerLabel }}
          </div>
          <div class="operations-board__live">LIVE</div>
          <q-btn
            flat
            round
            dense
            color="white"
            icon="remove"
            :aria-label="label('operations_board.zoom_out', 'Zoom out')"
            @click="adjustZoom(-10)"
          />
          <button
            type="button"
            class="operations-board__zoom-value"
            :aria-label="label('operations_board.zoom_reset', 'Reset zoom')"
            @click="resetZoom"
          >
            {{ zoomPercent }}%
          </button>
          <q-btn
            flat
            round
            dense
            color="white"
            icon="add"
            :aria-label="label('operations_board.zoom_in', 'Zoom in')"
            @click="adjustZoom(10)"
          />
          <q-btn
            flat
            round
            dense
            color="white"
            icon="refresh"
            :loading="loading"
            :aria-label="label('operations_board.refresh', 'Refresh')"
            @click="getList"
          />
          <q-btn
            flat
            round
            dense
            color="white"
            :icon="isFullscreen ? 'fullscreen_exit' : 'fullscreen'"
            :aria-label="isFullscreen
              ? label('operations_board.exit_fullscreen', 'Exit fullscreen')
              : label('operations_board.fullscreen', 'Fullscreen')"
            @click="toggleFullscreen"
          />
        </q-card-section>

        <q-card-section class="operations-board__controls row items-center q-pa-none">
          <q-tabs
            v-model="activeFilter"
            dense
            align="left"
            active-color="primary"
            indicator-color="primary"
            class="operations-board__filters"
          >
            <q-tab v-for="filter in filters" :key="filter.key" :name="filter.key" :label="filter.label" />
          </q-tabs>
          <q-space />
        </q-card-section>

        <q-table
          class="operations-board__table"
          table-class="operations-board__grid"
          :data="filteredItems"
          :columns="columns"
          row-key="id"
          dense
          flat
          bordered
          separator="horizontal"
          hide-bottom
          :row-class="rowClass"
          :loading="loading"
          :pagination.sync="pagination"
          :no-data-label="noDataLabel"
        >
          <template v-slot:body-cell-lane="props">
            <q-td :props="props">
              <q-badge :color="laneColor(props.value)" align="middle">
                {{ laneLabel(props.value) }}
              </q-badge>
            </q-td>
          </template>
          <template v-slot:body-cell-quantity="props">
            <q-td :props="props" class="text-weight-medium">
              {{ props.row.quantity }} / {{ props.row.total_quantity }}
            </q-td>
          </template>
          <template v-slot:body-cell-eta="props">
            <q-td :props="props">
              <div class="operations-board__eta-value">
                {{ props.row.eta || label('operations_board.eta_not_provided', 'Not Provided') }}
                <q-badge
                  outline
                  :color="etaStatusColor(props.row.eta_status)"
                  class="operations-board__eta-status"
                >
                  {{ etaStatusLabel(props.row.eta_status) }}
                </q-badge>
              </div>
              <div v-if="etaCountdown(props.row)" class="operations-board__eta-countdown">
                {{ etaCountdown(props.row) }}
              </div>
            </q-td>
          </template>
          <template v-slot:body-cell-customer="props">
            <q-td :props="props">
              <span :title="props.row.customer_full_name || props.row.customer">
                {{ props.row.customer || label('operations_board.customer_not_provided', 'Not Provided') }}
              </span>
            </q-td>
          </template>
          <template v-slot:body-cell-assigned_to="props">
            <q-td :props="props">
              {{ props.row.assignee_name || assignedRoleLabel(props.row.assigned_role) }}
            </q-td>
          </template>
          <template v-slot:body-cell-operation="props">
            <q-td :props="props">{{ operationLabel(props.value) }}</q-td>
          </template>
          <template v-slot:body-cell-business_status="props">
            <q-td :props="props">
              <q-badge :color="businessStatusColor(props.row.business_status)">
                {{ businessStatusLabel(props.row.business_status) }}
              </q-badge>
            </q-td>
          </template>
          <template v-slot:body-cell-category="props">
            <q-td :props="props">
              <q-badge outline color="primary" class="operations-board__type">
                {{ categoryLabel(props.value) }}
              </q-badge>
            </q-td>
          </template>
          <template v-slot:body-cell-location="props">
            <q-td :props="props">
              <span :title="label('operations_board.location_hint', 'Target area for this step, not current inventory location')">
                {{ locationLabel(props.value) }}
              </span>
              <div v-if="props.row.category === 'inbound'" class="text-caption text-grey-6">
                R {{ props.row.staging_reserved_qty || 0 }} / O {{ props.row.staging_occupied_qty || 0 }}
              </div>
            </q-td>
          </template>
          <template v-slot:body-cell-action="props">
            <q-td :props="props">
              <q-btn
                flat
                dense
                color="primary"
                icon="open_in_new"
                :aria-label="label('operations_board.open', 'Open')"
                @click="openItem(props.row)"
              />
            </q-td>
          </template>
        </q-table>
      </q-card>
    </div>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'OperationsBoard',
  data () {
    return {
      activeFilter: 'all',
      items: [],
      viewer: { staff_name: '', staff_type: '', scope: '' },
      loading: false,
      refreshTimer: null,
      pagination: { rowsPerPage: 10 },
      isFullscreen: false,
      zoomPercent: 100
    }
  },
  computed: {
    filters () {
      return [
        { key: 'all', label: this.label('operations_board.all', 'All') },
        { key: 'urgent', label: this.label('operations_board.urgent', 'Urgent') },
        { key: 'now', label: this.label('operations_board.now', 'Now') },
        { key: 'next', label: this.label('operations_board.next', 'Pending') },
        { key: 'delayed', label: this.label('operations_board.delayed', 'Delayed') },
        { key: 'blocked', label: this.label('operations_board.blocked', 'Blocked') }
      ]
    },
    noDataLabel () {
      return this.label('operations_board.no_work', 'No active warehouse work')
    },
    filteredItems () {
      if (this.activeFilter === 'all') return this.items
      if (this.activeFilter === 'urgent') {
        return this.items.filter(item => ['DUE_SOON', 'OVERDUE'].includes(item.eta_status))
      }
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
        { name: 'customer', label: this.label('operations_board.customer', 'Owner / Customer'), field: 'customer', align: 'left' },
        { name: 'assigned_to', label: this.label('operations_board.assigned_to', 'Assigned To'), field: 'assigned_to', align: 'left' },
        { name: 'category', label: this.label('operations_board.type', 'Type'), field: 'category', align: 'left' },
        { name: 'operation', label: this.label('operations_board.operation', 'Next Step'), field: 'operation', align: 'left' },
        { name: 'reference', label: this.label('operations_board.reference', 'Reference'), field: 'reference', align: 'left' },
        { name: 'location', label: this.label('operations_board.location', 'Target Area'), field: 'location', align: 'left' },
        { name: 'quantity', label: this.label('operations_board.quantity', 'Remaining / Total'), field: 'quantity', align: 'right' },
        { name: 'business_status', label: this.label('operations_board.status', 'Status'), field: 'business_status', align: 'left' },
        { name: 'action', label: '', field: 'action', align: 'right' }
      ]
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
    getList () {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth('dashboard/operations/?view=active&limit=200')
        .then(res => {
          this.items = res.items || []
          this.viewer = res.viewer || { staff_name: '', staff_type: '', scope: '' }
        })
        .catch(() => {})
        .finally(() => {
          this.loading = false
        })
    },
    laneLabel (lane) {
      return this.label(`operations_board.${lane}`, lane)
    },
    categoryLabel (category) {
      const key = String(category || '').toLowerCase()
      return this.label(`operations_board.${key}`, category)
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
      if (value === 'COMPLETED' || value === 'MATCHED') return 'positive'
      if (value === 'CANCELLED' || value.includes('EXCEPTION') || value === 'DISPUTED') return 'negative'
      if (value.includes('PENDING') || value === 'PRE_ARRIVAL') return 'primary'
      return 'grey-7'
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
    laneColor (lane) {
      return {
        now: 'positive',
        next: 'primary',
        delayed: 'warning',
        blocked: 'negative',
        completed: 'positive',
        cancelled: 'negative'
      }[lane] || 'grey'
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
      if (status === 'OVERDUE') {
        return `${this.label('operations_board.eta_overdue_by', 'Overdue by')} ${duration}`
      }
      return `${this.label('operations_board.eta_due_in', 'Due in')} ${duration}`
    },
    loadZoom () {
      const savedZoom = Number(window.localStorage.getItem('greaterwms.dashboard.zoom'))
      if (savedZoom >= 80 && savedZoom <= 140 && savedZoom % 10 === 0) {
        this.zoomPercent = savedZoom
      }
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
        this.$q.notify({
          message: this.label('operations_board.fullscreen_unavailable', 'Fullscreen is not supported by this browser'),
          color: 'negative',
          icon: 'fullscreen'
        })
        return
      }
      const result = request.call(target)
      if (result && result.catch) result.catch(() => {})
    },
    openItem (item) {
      if (!item.action_route) return
      const query = { reference: item.reference }
      if (item.category === 'inbound') query.asn_code = item.reference
      if (item.category === 'receiving') query.receipt_no = item.reference
      if (item.category === 'outbound') query.dn_code = item.reference
      if (item.category === 'transport') query.transport_no = item.reference
      this.$router.push({ name: item.action_route, query })
    }
  }
}
</script>

<style scoped>
.operations-board-shell {
  width: 100%;
}

.operations-board__surface {
  width: 100%;
}

.operations-board-shell--fullscreen {
  box-sizing: border-box;
  width: 100vw;
  height: 100vh;
  padding: 12px;
  overflow: auto;
  background: #edf1f5;
}

.operations-board-shell--fullscreen .operations-board__surface {
  width: calc(100% / var(--board-scale, 1));
  transform: scale(var(--board-scale, 1));
  transform-origin: top left;
}

.operations-board-shell--fullscreen .operations-board {
  min-height: calc(100vh - 24px);
  border-radius: 0;
}

.operations-board {
  width: 100%;
  background: #ffffff;
  border-radius: 2px;
}

.operations-board__header {
  min-height: 48px;
  background: #596782;
  color: #ffffff;
}

.operations-board__title {
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.operations-board__live {
  margin-right: 8px;
  color: #8ee3a7;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.operations-board__zoom-value {
  min-width: 42px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #ffffff;
  cursor: pointer;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.operations-board__eta-value {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.operations-board__eta-status {
  font-size: 10px;
  line-height: 1.2;
}

.operations-board__eta-countdown {
  margin-top: 2px;
  color: #6b7280;
  font-size: 11px;
  font-weight: 600;
}

.operations-board__viewer {
  margin-right: 16px;
  color: #e8edf7;
  font-size: 11px;
  letter-spacing: 0.04em;
}

.operations-board__controls {
  min-height: 38px;
  background: #f5f6f8;
  border-bottom: 1px solid #dfe3ea;
}

.operations-board__filters {
  min-height: 38px;
}

.operations-board__table >>> .q-table thead tr th {
  height: 38px;
  background: #3f4b69;
  color: #ffffff;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.operations-board__table >>> .q-table__middle {
  width: 100%;
  overflow-x: auto;
}

.operations-board__table >>> .q-table {
  min-width: 1040px;
}

.operations-board__table >>> .q-table th,
.operations-board__table >>> .q-table td {
  white-space: nowrap;
}

.operations-board__table >>> .q-table tbody tr {
  height: 48px;
}

.operations-board__table >>> .q-table tbody tr:nth-child(even) {
  background: #f7f8fb;
}

.operations-board__table >>> .q-table tbody tr:hover {
  background: #eaf0f8;
}

.operations-board__type {
  min-width: 64px;
  justify-content: center;
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

@media (max-width: 599px) {
  .operations-board__table >>> .q-table {
    min-width: 1040px;
  }
}
</style>
