<template>
  <div class="q-pa-md transport-page">
    <div class="row items-center q-mb-sm">
      <div class="text-h6">Local Transport</div>
      <q-space />
      <q-btn flat round icon="refresh" :loading="loading" @click="reload" />
    </div>
    <q-table
      flat
      bordered
      dense
      row-key="id"
      :data="rows"
      :columns="columns"
      :loading="loading"
      :pagination.sync="pagination"
      :rows-per-page-options="[10, 30, 50, 100]"
      no-data-label="No transport orders"
      @request="onRequest"
    >
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-badge :color="statusColor(props.row.status)">{{ props.row.status }}</q-badge>
        </q-td>
      </template>
    </q-table>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'TransportOrders',
  data () {
    return {
      loading: false,
      rows: [],
      pagination: {
        page: 1,
        rowsPerPage: 30,
        rowsNumber: 0
      },
      requestId: 0,
      columns: [
        { name: 'transport_no', label: 'Transport', field: 'transport_no', align: 'left' },
        { name: 'direction', label: 'Direction', field: 'direction', align: 'left' },
        { name: 'reference_no', label: 'Reference', field: 'reference_no', align: 'left' },
        { name: 'customer', label: 'Customer', field: 'customer', align: 'left' },
        { name: 'driver_name', label: 'Driver', field: 'driver_name', align: 'left' },
        { name: 'eta', label: 'ETA', field: 'eta', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'left' }
      ]
    }
  },
  mounted () {
    this.load()
  },
  watch: {
    '$route.query.transport_no' () {
      this.reload()
    }
  },
  methods: {
    reload () {
      this.load({
        ...this.pagination,
        page: 1
      })
    },
    onRequest (props) {
      this.load(props.pagination)
    },
    load (requestedPagination) {
      if (!this.$q.localStorage.has('auth')) return
      const pagination = requestedPagination || this.pagination
      const requestId = ++this.requestId
      this.loading = true
      const transportNo = this.$route.query && this.$route.query.transport_no
      const params = [
        'page=' + encodeURIComponent(pagination.page),
        'max_page=' + encodeURIComponent(pagination.rowsPerPage)
      ]
      if (transportNo) params.push('transport_no=' + encodeURIComponent(transportNo))
      const path = 'transport/orders/?' + params.join('&')
      getauth(path)
        .then(response => {
          if (requestId !== this.requestId) return
          this.rows = response.results || []
          this.pagination = {
            ...pagination,
            rowsNumber: Number(response.count || 0)
          }
        })
        .catch(() => {
          if (requestId === this.requestId) {
            this.$q.notify({ type: 'negative', message: 'Unable to load transport orders' })
          }
        })
        .finally(() => {
          if (requestId === this.requestId) this.loading = false
        })
    },
    statusColor (status) {
      if (status === 'CANCELLED') return 'negative'
      if (status === 'COMPLETED') return 'positive'
      if (status === 'IN_TRANSIT') return 'primary'
      return 'grey-7'
    }
  }
}
</script>
