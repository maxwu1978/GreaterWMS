<template>
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
        icon="refresh"
        :loading="loading"
        :aria-label="label('operations_board.refresh', 'Refresh')"
        @click="getList"
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
      :no-data-label="label('operations_board.no_work', 'No active warehouse work')"
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
          {{ props.row.eta || label('operations_board.eta_not_provided', 'Not Provided') }}
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
      pagination: { rowsPerPage: 10 }
    }
  },
  computed: {
    filters () {
      return [
        { key: 'all', label: this.label('operations_board.all', 'All') },
        { key: 'now', label: this.label('operations_board.now', 'Now') },
        { key: 'next', label: this.label('operations_board.next', 'Pending') },
        { key: 'delayed', label: this.label('operations_board.delayed', 'Delayed') },
        { key: 'blocked', label: this.label('operations_board.blocked', 'Blocked') }
      ]
    },
    filteredItems () {
      if (this.activeFilter === 'all') return this.items
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
        { name: 'eta', label: this.label('operations_board.eta', 'ETA'), field: 'eta', align: 'left' },
        { name: 'customer', label: this.label('operations_board.customer', 'Owner / Customer'), field: 'customer', align: 'left' },
        { name: 'assigned_to', label: this.label('operations_board.assigned_to', 'Assigned To'), field: 'assigned_to', align: 'left' },
        { name: 'category', label: this.label('operations_board.type', 'Type'), field: 'category', align: 'left' },
        { name: 'operation', label: this.label('operations_board.operation', 'Next Step'), field: 'operation', align: 'left' },
        { name: 'reference', label: this.label('operations_board.reference', 'Reference'), field: 'reference', align: 'left' },
        { name: 'location', label: this.label('operations_board.location', 'Target Area'), field: 'location', align: 'left' },
        { name: 'quantity', label: this.label('operations_board.quantity', 'Remaining / Total'), field: 'quantity', align: 'right' },
        { name: 'lane', label: this.label('operations_board.status', 'Work Status'), field: 'lane', align: 'left' },
        { name: 'action', label: '', field: 'action', align: 'right' }
      ]
    }
  },
  mounted () {
    this.getList()
    this.refreshTimer = setInterval(() => this.getList(), 30000)
  },
  beforeDestroy () {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
  },
  methods: {
    label (key, fallback) {
      const translated = this.$t(key)
      return translated === key ? fallback : translated
    },
    getList () {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth('dashboard/operations/')
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
    locationLabel (location) {
      const key = String(location || '').toLowerCase()
      return this.label(`operations_board.${key}`, location)
    },
    assignedRoleLabel (role) {
      const labels = {
        DRIVER: this.label('operations_board.driver', 'Driver'),
        QC: this.label('operations_board.qc', 'QC'),
        WAREHOUSE: this.label('operations_board.warehouse', 'Warehouse')
      }
      return labels[String(role || '').toUpperCase()] || role || ''
    },
    laneColor (lane) {
      return {
        now: 'positive',
        next: 'primary',
        delayed: 'warning',
        blocked: 'negative'
      }[lane] || 'grey'
    },
    rowClass (row) {
      return `operations-board__row--${row.lane || 'default'}`
    },
    openItem (item) {
      if (item.action_route) this.$router.push({ name: item.action_route })
    }
  }
}
</script>

<style scoped>
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
