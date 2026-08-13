<template>
  <div class="q-pa-sm packlist-page">
    <div class="row items-center q-col-gutter-sm">
      <div class="col-12 col-md-5 col-lg-3">
        <q-select
          v-model="asnCode"
          outlined
          dense
          emit-value
          map-options
          :options="asnOptions"
          label="ASN"
          @input="loadDocuments"
        />
      </div>
      <div class="col text-caption text-grey-7">
        Pack List and QC results are imported by the AI Agent / CLI.
      </div>
    </div>

    <q-banner v-if="summary" dense class="q-mt-sm q-pa-sm" :class="summary.reconciliation_status === 'EXCEPTION' ? 'bg-red-1' : (summary.reconciliation_status === 'PASSED' ? 'bg-green-1' : 'bg-orange-1')">
      <div class="row items-center q-col-gutter-sm">
        <div class="col-12 col-md-3">
          <div class="text-subtitle2">{{ summary.customer_short_name || summary.customer || '-' }} · {{ asnCode }}</div>
        </div>
        <div class="col-6 col-md-2"><q-chip dense :color="statusColor(summary.reconciliation_status)">{{ statusLabel(summary.reconciliation_status) }}</q-chip></div>
        <div class="col-6 col-md-2 text-caption">Pack List: <strong>{{ packListLabel(summary.pack_list_status) }}</strong></div>
        <div class="col-6 col-md-2 text-caption">QC: <strong>{{ summary.qc_status || 'NOT_STARTED' }}</strong></div>
        <div class="col-6 col-md-2 text-caption">Customer SN: <strong>{{ summary.customer_sn_status || 'NOT_PROVIDED' }}</strong></div>
        <div class="col-6 col-md-1 text-caption">ETA: <strong>{{ etaLabel }}</strong></div>
      </div>
      <div v-if="summary.receiving_summary" class="text-caption q-mt-xs">
        Received: <strong>{{ summary.receiving_summary.received_qty || 0 }}</strong> · Accepted: <strong>{{ summary.receiving_summary.accepted || 0 }}</strong> · Putaway: <strong>{{ summary.receiving_summary.accepted_for_putaway || 0 }}</strong> · Exceptions: <strong>{{ summary.receiving_summary.open_exceptions || 0 }}</strong><span v-if="summary.receiving_summary.extra_scan_records"> · Extra scans: {{ summary.receiving_summary.extra_scan_records }}</span>
      </div>
      <div v-if="summary.pack_list_status === 'PENDING' || summary.pack_list_status === 'LATE_PENDING'" class="text-caption text-orange-10 q-mt-xs">Pack List pending confirmation.</div>
      <div v-else-if="summary.pack_list_timing === 'LATE_REFERENCE'" class="text-caption text-blue-10 q-mt-xs">Late reference revision.</div>
    </q-banner>

    <q-table
      v-if="summary"
      class="q-mt-sm shadow-24 reconciliation-table"
      flat
      bordered
      dense
      row-key="goods_code"
      :data="reconciliationRows"
      :columns="reconciliationColumns"
      no-data-label="No reconciliation rows"
    >
      <template v-slot:body-cell-customer_goods_code="props">
        <q-td :props="props" class="ellipsis-cell">
          <span>{{ props.value || '-' }}</span>
          <q-tooltip v-if="props.value">{{ props.value }}</q-tooltip>
        </q-td>
      </template>
      <template v-slot:body-cell-variance="props">
        <q-td :props="props" :class="Number(props.value) ? 'text-negative text-weight-medium' : 'text-positive'">
          {{ props.value > 0 ? '+' : '' }}{{ props.value }}
        </q-td>
      </template>
      <template v-slot:body-cell-result="props">
        <q-td :props="props">
          <q-chip dense :color="statusColor(props.value)">{{ statusLabel(props.value) }}</q-chip>
        </q-td>
      </template>
      <template v-slot:body-cell-detail="props">
        <q-td :props="props">
          <q-btn dense flat round color="primary" icon="fact_check" @click="showReconciliation(props.row)">
            <q-tooltip>View receiving details</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <q-table
      class="q-mt-sm my-sticky-header-table shadow-24"
      flat
      bordered
      dense
      row-key="id"
      :data="documents"
      :columns="columns"
      :loading="loading"
      no-data-label="No Customer Pack List"
    >
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-chip dense :color="props.value === 'CONFIRMED' ? 'positive' : 'orange-3'">{{ props.value }}</q-chip>
        </q-td>
      </template>
      <template v-slot:body-cell-timing="props">
        <q-td :props="props">{{ props.row.late_reference ? 'Late reference' : 'Before receipt' }}</q-td>
      </template>
      <template v-slot:body-cell-action="props">
        <q-td :props="props">
          <q-btn dense flat round color="info" icon="visibility" @click="showDocument(props.row)">
            <q-tooltip>View Pack List</q-tooltip>
          </q-btn>
        </q-td>
      </template>
    </q-table>

    <q-table
      class="q-mt-sm"
      flat
      bordered
      dense
      row-key="id"
      :data="inspectionBatches"
      :columns="inspectionColumns"
      no-data-label="No QC inspection imported"
    >
      <template v-slot:top-left><div class="text-subtitle2">QC Inspection History</div></template>
      <template v-slot:body-cell-created_at="props">
        <q-td :props="props">{{ formatDate(props.value) }}</q-td>
      </template>
      <template v-slot:body-cell-status="props">
        <q-td :props="props"><q-chip dense :color="inspectionColor(props.value)">{{ props.value }}</q-chip></q-td>
      </template>
    </q-table>

    <q-dialog v-model="detailOpen">
      <q-card style="width: 900px; max-width: 95vw">
        <q-bar class="bg-light-blue-10 text-white">
          <div>{{ selectedDocument ? selectedDocument.asn_code + ' / Customer Pack List revision ' + selectedDocument.version : 'Customer Pack List' }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section v-if="selectedDocument">
          <div class="row q-col-gutter-md text-caption q-mb-sm">
            <div class="col-6 col-md-3">Status: {{ selectedDocument.status }}</div>
            <div class="col-6 col-md-3">Lines: {{ selectedDocument.line_count }}</div>
            <div class="col-6 col-md-3">Qty: {{ selectedDocument.total_qty }}</div>
            <div class="col-6 col-md-3">SN: {{ selectedDocument.expected_serial_count }}</div>
            <div class="col-6 col-md-3">Load units: {{ selectedDocument.package_qty || 'Not provided' }}</div>
            <div class="col-6 col-md-3">Customer SN: {{ selectedDocument.has_serials ? 'PROVIDED' : 'NOT_PROVIDED' }}</div>
            <div class="col-6 col-md-3">Timing: {{ selectedDocument.late_reference ? 'LATE_REFERENCE' : 'BEFORE_RECEIPT' }}</div>
          </div>
          <q-list bordered separator>
            <q-item v-for="(line, index) in selectedDocument.lines" :key="index">
              <q-item-section>
                <q-item-label>{{ line.goods_code }}</q-item-label>
                <q-item-label caption v-if="line.customer_goods_code">Customer SKU: {{ line.customer_goods_code }}</q-item-label>
                <q-item-label caption v-if="line.customer_ssku">Customer S-SKU: {{ line.customer_ssku }}</q-item-label>
                <q-item-label caption v-if="line.package_type">Package: {{ line.package_type }}</q-item-label>
              </q-item-section>
              <q-item-section side>{{ line.goods_qty }}</q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>
    </q-dialog>

    <q-dialog v-model="reconciliationOpen">
      <q-card style="width: 680px; max-width: 95vw">
        <q-bar class="bg-light-blue-10 text-white">
          <div>Receiving Reconciliation</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section v-if="selectedReconciliation" class="row q-col-gutter-md text-caption">
          <div class="col-6 col-md-4">SKU: <strong>{{ selectedReconciliation.goods_code }}</strong></div>
          <div class="col-6 col-md-4">Customer SKU: <strong>{{ selectedReconciliation.customer_goods_code || '-' }}</strong></div>
          <div class="col-6 col-md-4">Result: <q-chip dense :color="statusColor(selectedReconciliation.result)">{{ statusLabel(selectedReconciliation.result) }}</q-chip></div>
          <div class="col-6 col-md-3">Pack List: <strong>{{ selectedReconciliation.pack_list_qty }}</strong></div>
          <div class="col-6 col-md-3">Received: <strong>{{ selectedReconciliation.received_qty }}</strong></div>
          <div class="col-6 col-md-3">Accepted: <strong>{{ selectedReconciliation.accepted_qty }}</strong></div>
          <div class="col-6 col-md-3">Variance: <strong>{{ selectedReconciliation.variance }}</strong></div>
          <div class="col-6 col-md-3">Open exceptions: <strong>{{ selectedReconciliation.open_exception_count }}</strong></div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request'

export default {
  name: 'Pagepacklist',
  data () {
    return {
      asnCode: this.$route.query.asn_code || '',
      asnOptions: [],
      documents: [],
      inspectionBatches: [],
      summary: null,
      loading: false,
      detailOpen: false,
      selectedDocument: null,
      reconciliationOpen: false,
      selectedReconciliation: null,
      columns: [
        { name: 'version', label: 'Revision', field: 'version', align: 'center' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'timing', label: 'Timing', field: 'late_reference', align: 'center' },
        { name: 'total_qty', label: 'Qty', field: 'total_qty', align: 'center' },
        { name: 'package_qty', label: 'Load Units', field: 'package_qty', align: 'center' },
        { name: 'expected_serial_count', label: 'SN', field: 'expected_serial_count', align: 'center' },
        { name: 'action', label: 'View', align: 'right' }
      ],
      inspectionColumns: [
        { name: 'id', label: 'Round', field: 'id', align: 'center' },
        { name: 'created_at', label: 'Imported', field: 'created_at', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'matched_count', label: 'Scanned', field: 'matched_count', align: 'center' },
        { name: 'accepted_count', label: 'Accepted', field: 'accepted_count', align: 'center' },
        { name: 'exception_count', label: 'Exceptions', field: 'exception_count', align: 'center' }
      ],
      reconciliationColumns: [
        { name: 'goods_code', label: 'SKU', field: 'goods_code', align: 'left', style: 'width: 13%;', headerStyle: 'width: 13%;' },
        { name: 'customer_goods_code', label: 'Customer SKU', field: 'customer_goods_code', align: 'left', style: 'width: 18%;', headerStyle: 'width: 18%;' },
        { name: 'pack_list_qty', label: 'Pack List', field: 'pack_list_qty', align: 'center', style: 'width: 9%;', headerStyle: 'width: 9%;' },
        { name: 'received_qty', label: 'Received', field: 'received_qty', align: 'center', style: 'width: 9%;', headerStyle: 'width: 9%;' },
        { name: 'accepted_qty', label: 'Accepted', field: 'accepted_qty', align: 'center', style: 'width: 9%;', headerStyle: 'width: 9%;' },
        { name: 'variance', label: 'Variance', field: 'variance', align: 'center', style: 'width: 9%;', headerStyle: 'width: 9%;' },
        { name: 'open_exception_count', label: 'Open', field: 'open_exception_count', align: 'center', style: 'width: 8%;', headerStyle: 'width: 8%;' },
        { name: 'result', label: 'Result', field: 'result', align: 'center', style: 'width: 14%;', headerStyle: 'width: 14%;' },
        { name: 'detail', label: '', align: 'center', style: 'width: 5%;', headerStyle: 'width: 5%;' }
      ]
    }
  },
  computed: {
    reconciliationRows () {
      return this.summary && this.summary.reconciliation_rows ? this.summary.reconciliation_rows : []
    },
    etaLabel () {
      if (!this.summary) return 'Not provided'
      if (this.summary.actual_arrival_at) return 'Arrived ' + this.formatDate(this.summary.actual_arrival_at)
      return this.summary.expected_arrival_at ? this.formatDate(this.summary.expected_arrival_at) : 'Not provided'
    }
  },
  created () {
    this.loadAsns()
  },
  methods: {
    loadAsns () {
      getauth('asn/list/?page=1').then(res => {
        this.asnOptions = (res.results || []).map(item => ({ label: item.asn_code, value: item.asn_code }))
        if (!this.asnCode && this.asnOptions.length) this.asnCode = this.asnOptions[0].value
        if (this.asnCode) this.loadDocuments()
      }).catch(() => {})
    },
    loadDocuments () {
      if (!this.asnCode) return
      this.loading = true
      getauth('asn/serial/packlists/?asn_code=' + encodeURIComponent(this.asnCode)).then(res => {
        this.documents = res.results || []
        this.summary = res.summary
        this.inspectionBatches = res.inspection_batches || (res.summary && res.summary.inspection_batches) || []
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to load Pack List', color: 'negative' })
      }).then(() => {
        this.loading = false
      })
    },
    showDocument (document) {
      this.selectedDocument = document
      this.detailOpen = true
    },
    showReconciliation (row) {
      this.selectedReconciliation = row
      this.reconciliationOpen = true
    },
    statusLabel (status) {
      return {
        REVIEW: 'Review Required',
        EXCEPTION: 'Exception',
        PASSED: 'Passed',
        RESOLVED: 'Resolved'
      }[status] || status || 'Unknown'
    },
    statusColor (status) {
      return {
        REVIEW: 'orange-3',
        EXCEPTION: 'red-3',
        PASSED: 'green-3',
        RESOLVED: 'blue-3'
      }[status] || 'grey-3'
    },
    packListLabel (status) {
      return {
        PENDING: 'Pending',
        CONFIRMED: 'Confirmed',
        LATE: 'Late reference',
        LATE_PENDING: 'Late / pending',
        NOT_RECEIVED: 'Not Received'
      }[status] || status || 'Not Received'
    },
    inspectionColor (status) {
      return {
        PASSED: 'positive',
        EXCEPTION: 'negative',
        PARTIAL: 'warning',
        IMPORTED: 'grey-6'
      }[status] || 'grey-6'
    },
    formatDate (value) {
      return String(value || '').replace('T', ' ').slice(0, 16) || 'Not provided'
    }
  }
}
</script>

<style scoped>
.packlist-page {
  box-sizing: border-box;
  min-width: 0;
  min-height: 0;
  padding-bottom: 24px;
}

.reconciliation-table .ellipsis-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
