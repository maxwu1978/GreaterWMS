<template>
  <q-dialog :value="value" @input="$emit('input', $event)">
    <q-card class="qc-review-card">
      <q-bar class="bg-light-blue-10 text-white">
        <div>QC Review - {{ asnCode }}</div>
        <q-space />
        <q-btn dense flat icon="close" v-close-popup />
      </q-bar>

      <q-card-section class="qc-review-content q-gutter-sm">
        <div class="row q-col-gutter-sm qc-context-grid">
          <div class="col-6 col-md-3"><span class="qc-label">Owner</span><strong>{{ ownerLabel }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">Staging</span><strong>{{ stagingLabel }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">Unload driver</span><strong>{{ asnContext.unload_driver || 'Not assigned' }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">Putaway driver</span><strong>{{ asnContext.putaway_driver || 'Not assigned' }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">Pack List</span><strong>{{ packListLabel(summary && summary.pack_list_status) }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">QC source</span><strong>{{ qcSourceLabel }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">QC result</span><strong>{{ qcStatusLabel }}</strong></div>
          <div class="col-6 col-md-3"><span class="qc-label">Arrival</span><strong>{{ arrivalLabel }}</strong></div>
        </div>

        <q-select
          v-if="goodsOptions.length > 1"
          v-model="selectedGoodsCode"
          outlined
          dense
          emit-value
          map-options
          :options="goodsOptions"
          label="SKU"
          @input="refreshSerialData"
        />

        <q-banner v-if="summary" dense class="qc-decision-banner" :class="bannerClass">
          <div class="text-weight-medium">{{ decisionBanner }}</div>
          <div class="text-caption q-mt-xs">{{ summary.verification_note || 'QC result is recorded in GreaterWMS.' }}</div>
        </q-banner>

        <div class="row q-col-gutter-sm qc-metrics">
          <div class="col-6 col-sm-3"><q-chip color="blue-1">Planned: {{ selectedLine.planned_qty || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="blue-1">Received: {{ selectedLine.received_qty || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="green-2">Accepted: {{ selectedLine.accepted_serial_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="purple-2">Eligible: {{ eligibleForPutaway }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="amber-2">Held: {{ selectedLine.held_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="orange-2">Rejected: {{ selectedLine.rejected_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip :color="selectedLine.exception_count ? 'red-2' : 'grey-3'">Open: {{ selectedLine.exception_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="grey-3">Putaway done: {{ (summary && summary.total_putaway_qty) || 0 }}</q-chip></div>
        </div>

        <div v-if="quantityExceptionQty" class="row items-center q-gutter-sm">
          <q-chip color="orange-2">Quantity exception: {{ quantityExceptionLabel }}</q-chip>
          <q-btn
            dense
            flat
            color="primary"
            :label="selectedLine.exception_resolved ? 'Reopen quantity decision' : 'Resolve quantity exception'"
            @click="openQuantityResolution"
          />
        </div>

        <div v-if="latestInspection" class="qc-import-summary">
          <span>QC import: <strong>{{ latestInspection.status }}</strong></span>
          <span>{{ latestInspection.matched_count || 0 }} scanned</span>
          <span>{{ latestInspection.accepted_count || 0 }} accepted</span>
          <span>{{ latestInspection.exception_count || 0 }} exceptions</span>
          <span>{{ formatDate(latestInspection.created_at) }}</span>
          <a v-if="latestInspection.evidence_url" :href="latestInspection.evidence_url" target="_blank" rel="noopener">Evidence</a>
        </div>

        <q-separator />
        <div class="text-subtitle2">QC records</div>
        <q-table
          class="qc-record-table"
          dense
          flat
          bordered
          row-key="id"
          :data="records"
          :columns="recordColumns"
          :pagination.sync="pagination"
          :table-style="{ minWidth: '880px' }"
          no-data-label="No QC records"
        >
          <template v-slot:body-cell-status="props">
            <q-td :props="props">
              <q-chip dense square :color="recordStatusColor(props.value)">{{ recordStatusLabel(props.value) }}</q-chip>
            </q-td>
          </template>
          <template v-slot:body-cell-note="props">
            <q-td :props="props" class="qc-ellipsis-cell">
              <span :title="props.value || ''">{{ props.value || '-' }}</span>
            </q-td>
          </template>
          <template v-slot:body-cell-evidence_url="props">
            <q-td :props="props">
              <a v-if="props.value" :href="props.value" target="_blank" rel="noopener">Open</a>
              <span v-else class="text-grey-6">-</span>
            </q-td>
          </template>
          <template v-slot:body-cell-disposition="props">
            <q-td :props="props">
              <q-chip v-if="props.row.exception_resolved" dense square :color="dispositionColor(props.row.exception_resolution_action)">
                {{ dispositionLabel(props.row.exception_resolution_action) }}
              </q-chip>
              <q-btn
                v-else-if="canResolve(props.row)"
                dense
                flat
                color="primary"
                label="Resolve"
                @click="openSerialResolution(props.row)"
              />
              <span v-else class="text-grey-6">-</span>
            </q-td>
          </template>
        </q-table>

        <div class="text-caption text-grey-7">
          QC completion controls putaway eligibility. Assign the putaway driver and final storage bin from the ASN putaway action after this review.
        </div>
      </q-card-section>
    </q-card>

    <q-dialog v-model="resolutionForm">
      <q-card class="qc-resolution-card">
        <q-bar class="bg-light-blue-10 text-white">
          <div>{{ resolutionTitle }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section class="q-gutter-sm">
          <q-select
            v-model="resolutionAction"
            outlined
            dense
            emit-value
            map-options
            :options="resolutionActionOptions"
            label="Disposition"
          />
          <q-input
            v-if="requiresLocation"
            v-model="resolutionLocation"
            outlined
            dense
            label="Hold / return location"
            hint="Required for a held or rejected item"
          />
          <q-input
            v-model="resolutionNote"
            outlined
            type="textarea"
            autogrow
            label="QC decision note"
            hint="Required for every disposition"
          />
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat label="Cancel" v-close-popup />
          <q-btn color="primary" label="Save decision" @click="submitResolution" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-dialog>
</template>

<script>
import { getauth, postauth } from '../boot/axios_request'

export default {
  name: 'AsnSerialPanel',
  props: {
    value: { type: Boolean, default: false },
    asnCode: { type: String, default: '' },
    goodsCode: { type: String, default: '' },
    asnContext: { type: Object, default: () => ({}) }
  },
  data () {
    return {
      details: [],
      selectedGoodsCode: this.goodsCode,
      summary: null,
      records: [],
      inspectionBatches: [],
      pagination: { page: 1, rowsPerPage: 10 },
      resolutionForm: false,
      resolutionType: 'serial',
      resolutionTarget: null,
      resolutionAction: '',
      resolutionNote: '',
      resolutionLocation: '',
      recordColumns: [
        { name: 'serial_number', label: 'SN', field: 'serial_number', align: 'left' },
        { name: 'goods_code', label: 'SKU', field: 'goods_code', align: 'left' },
        { name: 'status', label: 'QC Result', field: 'status', align: 'center' },
        { name: 'note', label: 'QC Note', field: 'note', align: 'left' },
        { name: 'evidence_url', label: 'Evidence', field: 'evidence_url', align: 'center' },
        { name: 'disposition', label: 'Disposition', field: 'exception_resolution_action', align: 'center' }
      ]
    }
  },
  computed: {
    ownerLabel () {
      return this.asnContext.supplier_short_name || this.asnContext.supplier || '-'
    },
    stagingLabel () {
      const slots = Array.isArray(this.asnContext.staging_bins) ? this.asnContext.staging_bins : []
      return slots.length ? slots.join(', ') : (this.asnContext.staging_bin || 'Not assigned')
    },
    arrivalLabel () {
      return this.formatDate(this.asnContext.actual_arrival_at || (this.summary && this.summary.actual_arrival_at))
    },
    selectedLine () {
      if (!this.summary || !this.selectedGoodsCode) return {}
      return this.summary.lines.find(item => item.goods_code === this.selectedGoodsCode) || {}
    },
    goodsOptions () {
      return this.details.map(detail => ({
        label: detail.goods_code,
        value: detail.goods_code
      }))
    },
    eligibleForPutaway () {
      return Number(this.selectedLine.eligible_for_putaway || this.selectedLine.accepted_for_putaway || 0)
    },
    quantityExceptionQty () {
      return Number(this.selectedLine.quantity_exception_qty || 0)
    },
    quantityExceptionLabel () {
      const parts = []
      if (this.selectedLine.goods_shortage_qty) parts.push('Shortage ' + this.selectedLine.goods_shortage_qty)
      if (this.selectedLine.goods_more_qty) parts.push('Overage ' + this.selectedLine.goods_more_qty)
      if (this.selectedLine.goods_damage_qty) parts.push('Damage ' + this.selectedLine.goods_damage_qty)
      return parts.join(' / ') || String(this.quantityExceptionQty)
    },
    latestInspection () {
      return (this.summary && this.summary.latest_inspection_batch) || this.inspectionBatches[0] || null
    },
    qcStatusLabel () {
      return this.summary && this.summary.qc_status ? this.summary.qc_status : 'NOT_STARTED'
    },
    qcSourceLabel () {
      if (this.latestInspection) return this.latestInspection.source_type || 'AI_AGENT'
      return this.summary && this.summary.verification_mode ? this.summary.verification_mode : 'ASN_ONLY'
    },
    openExceptionCount () {
      return Number((this.summary && this.summary.total_exception_serials) || 0) + Number((this.summary && this.summary.total_quantity_exceptions) || 0)
    },
    decisionBanner () {
      if (!this.summary) return 'Loading QC result.'
      if (this.openExceptionCount > 0) return 'QC action required. Resolve every open exception before putaway.'
      if (!this.summary.qc_complete) return 'QC result is incomplete. Review the imported acceptance result.'
      if (this.eligibleForPutaway < Number(this.selectedLine.received_qty || 0)) return 'QC complete with held or rejected units. Put away eligible quantity only.'
      return 'QC complete. Assign the putaway driver and final storage bin.'
    },
    bannerClass () {
      if (this.openExceptionCount > 0) return 'bg-orange-1'
      return this.summary && this.summary.qc_complete ? 'bg-green-1' : 'bg-orange-1'
    },
    resolutionTitle () {
      return this.resolutionType === 'quantity' ? 'Quantity disposition' : 'SN disposition'
    },
    requiresLocation () {
      return this.resolutionAction === 'HOLD_QUARANTINE' || this.resolutionAction === 'REJECT_RETURN'
    },
    resolutionActionOptions () {
      if (this.resolutionType === 'quantity') {
        return [
          { label: 'Accept for putaway', value: 'ACCEPT_FOR_PUTAWAY' },
          { label: 'Hold / quarantine', value: 'HOLD_QUARANTINE' },
          { label: 'Reject / return', value: 'REJECT_RETURN' },
          { label: 'Reopen', value: 'REOPEN' }
        ]
      }
      if (this.resolutionTarget && !this.resolutionTarget.is_received) {
        return [
          { label: 'Waive missing SN', value: 'WAIVE_MISSING' },
          { label: 'Reopen', value: 'REOPEN' }
        ]
      }
      return [
        { label: 'Accept for putaway', value: 'ACCEPT_FOR_PUTAWAY' },
        { label: 'Hold / quarantine', value: 'HOLD_QUARANTINE' },
        { label: 'Reject / return', value: 'REJECT_RETURN' },
        { label: 'Reopen', value: 'REOPEN' }
      ]
    }
  },
  watch: {
    value (opened) {
      if (opened) this.loadData()
    },
    goodsCode (value) {
      if (value) this.selectedGoodsCode = value
    }
  },
  methods: {
    loadData () {
      if (!this.asnCode) return
      const query = '?asn_code=' + encodeURIComponent(this.asnCode)
      getauth('asn/detail/' + query).then(detailResponse => {
        this.details = detailResponse.results || []
        if (!this.selectedGoodsCode && this.details.length) this.selectedGoodsCode = this.details[0].goods_code
        return Promise.all([
          getauth('asn/serial/summary/' + query),
          getauth('asn/serial/records/' + query + (this.selectedGoodsCode ? '&goods_code=' + encodeURIComponent(this.selectedGoodsCode) : '')),
          getauth('asn/serial/inspections/' + query)
        ]).then(([summary, records, inspections]) => {
          this.summary = summary
          this.records = records.results || []
          this.inspectionBatches = inspections.results || []
        })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to load QC review', color: 'negative' })
      })
    },
    canResolve (record) {
      return Boolean(record.exception_resolved || record.status === 'UNEXPECTED' || record.status === 'DUPLICATE' || record.status === 'WRONG_SKU' || record.status === 'DAMAGED' || record.status === 'REJECTED' || (record.is_expected && !record.is_received))
    },
    openSerialResolution (record) {
      this.resolutionType = 'serial'
      this.resolutionTarget = record
      this.resolutionAction = record.exception_resolved ? 'REOPEN' : (record.is_received ? 'ACCEPT_FOR_PUTAWAY' : 'WAIVE_MISSING')
      this.resolutionNote = record.exception_resolution_note || ''
      this.resolutionLocation = record.resolution_location || ''
      this.resolutionForm = true
    },
    openQuantityResolution () {
      this.resolutionType = 'quantity'
      this.resolutionTarget = this.selectedLine
      this.resolutionAction = this.selectedLine.exception_resolved ? 'REOPEN' : 'ACCEPT_FOR_PUTAWAY'
      this.resolutionNote = this.selectedLine.exception_resolution_note || ''
      this.resolutionLocation = this.selectedLine.resolution_location || ''
      this.resolutionForm = true
    },
    submitResolution () {
      if (!this.resolutionTarget) return
      if (this.resolutionAction !== 'REOPEN' && !this.resolutionNote.trim()) {
        this.$q.notify({ message: 'Enter a QC decision note', color: 'negative' })
        return
      }
      if (this.requiresLocation && !this.resolutionLocation.trim()) {
        this.$q.notify({ message: 'Enter a hold or return location', color: 'negative' })
        return
      }
      const isQuantity = this.resolutionType === 'quantity'
      const payload = isQuantity
        ? {
          asn_code: this.asnCode,
          goods_code: this.resolutionTarget.goods_code,
          action: this.resolutionAction,
          note: this.resolutionNote,
          resolution_location: this.resolutionLocation
        }
        : {
          id: this.resolutionTarget.id,
          action: this.resolutionAction,
          note: this.resolutionNote,
          resolution_location: this.resolutionLocation
        }
      const endpoint = isQuantity ? 'asn/serial/exceptions/resolve-quantity/' : 'asn/serial/exceptions/resolve/'
      postauth(endpoint, payload).then(() => {
        this.resolutionForm = false
        this.refreshSerialData()
        this.$q.notify({ message: 'QC disposition saved', color: 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to save QC disposition', color: 'negative' })
      })
    },
    refreshSerialData () {
      const query = '?asn_code=' + encodeURIComponent(this.asnCode)
      return Promise.all([
        getauth('asn/serial/summary/' + query),
        getauth('asn/serial/records/' + query + (this.selectedGoodsCode ? '&goods_code=' + encodeURIComponent(this.selectedGoodsCode) : '')),
        getauth('asn/serial/inspections/' + query)
      ]).then(([summary, records, inspections]) => {
        this.summary = summary
        this.records = records.results || []
        this.inspectionBatches = inspections.results || []
      })
    },
    recordStatusLabel (status) {
      return {
        ACCEPTED: 'Accepted',
        EXPECTED: 'Expected',
        UNVERIFIED: 'Unverified',
        UNEXPECTED: 'Unexpected',
        DUPLICATE: 'Duplicate',
        WRONG_SKU: 'Wrong SKU',
        DAMAGED: 'Damaged',
        REJECTED: 'Rejected'
      }[status] || status || '-'
    },
    recordStatusColor (status) {
      return {
        ACCEPTED: 'positive',
        EXPECTED: 'grey-4',
        UNVERIFIED: 'orange-3',
        DAMAGED: 'negative',
        REJECTED: 'negative',
        UNEXPECTED: 'orange-3',
        DUPLICATE: 'orange-3',
        WRONG_SKU: 'orange-3'
      }[status] || 'grey-4'
    },
    dispositionLabel (action) {
      return {
        ACCEPT_EXCEPTION: 'Accepted for Putaway',
        ACCEPT_FOR_PUTAWAY: 'Accepted for Putaway',
        HOLD_QUARANTINE: 'Held / Quarantine',
        REJECT_RETURN: 'Rejected / Return',
        WAIVE_MISSING: 'Missing SN Waived',
        REOPEN: 'Open'
      }[action] || '-'
    },
    dispositionColor (action) {
      return {
        ACCEPT_EXCEPTION: 'positive',
        ACCEPT_FOR_PUTAWAY: 'positive',
        HOLD_QUARANTINE: 'amber-3',
        REJECT_RETURN: 'negative',
        WAIVE_MISSING: 'orange-3',
        REOPEN: 'grey-4'
      }[action] || 'grey-4'
    },
    packListLabel (status) {
      return {
        PENDING: 'Pending',
        CONFIRMED: 'Confirmed',
        LATE: 'Late reference',
        LATE_PENDING: 'Late / pending',
        NOT_RECEIVED: 'Not received'
      }[status] || status || 'Not received'
    },
    formatDate (value) {
      return String(value || '').replace('T', ' ').slice(0, 16) || 'Not provided'
    }
  }
}
</script>

<style scoped>
.qc-review-card {
  width: 1120px;
  max-width: 96vw;
  max-height: 92vh;
  display: flex;
  flex-direction: column;
}

.qc-review-content {
  min-height: 0;
  overflow-y: auto;
}

.qc-context-grid > div {
  min-height: 34px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.qc-label {
  color: #6b7280;
  font-size: 11px;
  text-transform: uppercase;
}

.qc-decision-banner {
  border: 1px solid rgba(0, 0, 0, 0.08);
}

.qc-metrics .q-chip {
  width: 100%;
  justify-content: center;
  margin: 0;
}

.qc-import-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: #5f6368;
  font-size: 12px;
}

.qc-record-table {
  max-width: 100%;
}

.qc-ellipsis-cell {
  max-width: 230px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qc-resolution-card {
  width: 500px;
  max-width: 92vw;
}
</style>
