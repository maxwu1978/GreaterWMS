<template>
  <q-card class="operations-board shadow-11">
    <q-card-section class="row items-center q-pb-sm">
      <div>
        <div class="text-h6 text-grey-8 text-weight-bolder">
          {{ label('operations_board.title', 'Warehouse Operations') }}
        </div>
        <div class="text-caption text-grey-6 q-mt-xs">
          {{ label('operations_board.updated', 'Updated') }}: {{ updatedAt }}
        </div>
      </div>
      <q-space />
      <q-btn
        flat
        dense
        color="primary"
        icon="refresh"
        :loading="loading"
        :label="label('operations_board.refresh', 'Refresh')"
        @click="getList"
      />
    </q-card-section>

    <q-separator />

    <q-card-section class="q-pb-sm">
      <div class="row q-col-gutter-sm">
        <div v-for="summary in summaries" :key="summary.key" class="col-6 col-sm-3">
          <q-card flat bordered class="operations-board__summary" :class="`operations-board__summary--${summary.key}`">
            <q-card-section class="q-pa-sm">
              <div class="text-caption text-grey-7">{{ summary.label }}</div>
              <div class="text-h5 text-weight-bolder text-grey-9">{{ counts[summary.key] || 0 }}</div>
            </q-card-section>
          </q-card>
        </div>
      </div>

      <q-tabs
        v-model="activeFilter"
        dense
        align="left"
        active-color="primary"
        indicator-color="primary"
        class="q-mt-sm"
      >
        <q-tab v-for="filter in filters" :key="filter.key" :name="filter.key" :label="filter.label" />
      </q-tabs>
    </q-card-section>

    <q-separator />

    <q-table
      class="operations-board__table"
      :data="filteredItems"
      :columns="columns"
      row-key="id"
      flat
      bordered
      separator="cell"
      hide-bottom
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
      <template v-slot:body-cell-operation="props">
        <q-td :props="props">{{ operationLabel(props.value) }}</q-td>
      </template>
      <template v-slot:body-cell-location="props">
        <q-td :props="props">{{ locationLabel(props.value) }}</q-td>
      </template>
      <template v-slot:body-cell-action="props">
        <q-td :props="props">
          <q-btn
            flat
            dense
            color="primary"
            icon="open_in_new"
            :label="label('operations_board.open', 'Open')"
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
      counts: { total: 0, now: 0, next: 0, delayed: 0, blocked: 0 },
      generatedAt: '',
      items: [],
      loading: false,
      refreshTimer: null,
      pagination: { rowsPerPage: 10 }
    }
  },
  computed: {
    summaries () {
      return [
        { key: 'now', label: this.label('operations_board.now', 'Now') },
        { key: 'next', label: this.label('operations_board.next', 'Next') },
        { key: 'delayed', label: this.label('operations_board.delayed', 'Delayed') },
        { key: 'blocked', label: this.label('operations_board.blocked', 'Blocked') }
      ]
    },
    filters () {
      return [
        { key: 'all', label: this.label('operations_board.all', 'All') },
        ...this.summaries
      ]
    },
    filteredItems () {
      if (this.activeFilter === 'all') return this.items
      return this.items.filter(item => item.lane === this.activeFilter)
    },
    updatedAt () {
      if (!this.generatedAt) return '--'
      return this.generatedAt.replace('T', ' ').slice(0, 16)
    },
    columns () {
      return [
        { name: 'lane', label: this.label('operations_board.status', 'Status'), field: 'lane', align: 'left' },
        { name: 'time', label: this.label('operations_board.time', 'Time'), field: 'time', align: 'left' },
        { name: 'operation', label: this.label('operations_board.operation', 'Operation'), field: 'operation', align: 'left' },
        { name: 'reference', label: this.label('operations_board.reference', 'Reference'), field: 'reference', align: 'left' },
        { name: 'location', label: this.label('operations_board.location', 'Location'), field: 'location', align: 'left' },
        { name: 'quantity', label: this.label('operations_board.quantity', 'Remaining / Total'), field: 'quantity', align: 'right' },
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
          this.counts = res.counts || this.counts
          this.generatedAt = res.generated_at || ''
        })
        .catch(() => {})
        .finally(() => {
          this.loading = false
        })
    },
    laneLabel (lane) {
      return this.label(`operations_board.${lane}`, lane)
    },
    operationLabel (operation) {
      const key = String(operation || '').toLowerCase()
      return this.label(`operations_board.${key}`, operation)
    },
    locationLabel (location) {
      const key = String(location || '').toLowerCase()
      return this.label(`operations_board.${key}`, location)
    },
    laneColor (lane) {
      return {
        now: 'positive',
        next: 'primary',
        delayed: 'warning',
        blocked: 'negative'
      }[lane] || 'grey'
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
}

.operations-board__summary {
  border-left: 4px solid #606c88;
}

.operations-board__summary--now {
  border-left-color: #21ba45;
}

.operations-board__summary--next {
  border-left-color: #027be3;
}

.operations-board__summary--delayed {
  border-left-color: #f2c037;
}

.operations-board__summary--blocked {
  border-left-color: #c10015;
}

.operations-board__table >>> .q-table thead tr th {
  background: #f5f5f5;
  color: #606c88;
  font-weight: 700;
}

.operations-board__table >>> .q-table__middle {
  width: 100%;
  overflow-x: auto;
}

.operations-board__table >>> .q-table {
  min-width: 920px;
}

.operations-board__table >>> .q-table th,
.operations-board__table >>> .q-table td {
  white-space: nowrap;
}

.operations-board__table >>> .q-table tbody tr:hover {
  background: #f8f9fb;
}

@media (max-width: 599px) {
  .operations-board__table >>> .q-table {
    min-width: 760px;
  }
}
</style>
