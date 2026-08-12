<template>
  <q-dialog :value="value" @input="$emit('input', $event)">
    <q-card style="width: 960px; max-width: 96vw">
      <q-bar class="bg-light-blue-10 text-white">
        <div>SN Receiving Control - {{ asnCode }}</div>
        <q-space />
        <q-btn dense flat icon="close" v-close-popup />
      </q-bar>

      <q-card-section class="q-gutter-sm">
        <q-select
          v-model="selectedGoodsCode"
          outlined
          dense
          emit-value
          map-options
          :options="goodsOptions"
          label="SKU"
          @input="loadData"
        />

        <div class="row q-col-gutter-sm">
          <div class="col-6 col-sm-3"><q-chip color="blue-1">Planned: {{ selectedLine.planned_qty || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="grey-3">Expected SN: {{ selectedLine.expected_serial_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="green-2">Accepted: {{ selectedLine.accepted_serial_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip :color="selectedLine.exception_count ? 'red-2' : 'grey-3'">Exceptions: {{ selectedLine.exception_count || 0 }}</q-chip></div>
          <div class="col-6 col-sm-3"><q-chip color="blue-1">Resolved: {{ selectedLine.resolved_exception_count || 0 }}</q-chip></div>
          <div v-if="quantityExceptionQty" class="col-12 col-sm-6">
            <q-chip color="orange-2">{{ quantityExceptionLabel }}</q-chip>
            <q-btn
              dense
              flat
              color="primary"
              :label="selectedDetail.exception_resolved ? 'Reopen quantity exception' : 'Resolve quantity exception'"
              @click="openQuantityResolution"
            />
          </div>
        </div>

        <q-banner v-if="summary" :class="summary.ready_for_putaway ? 'bg-green-1' : 'bg-orange-1'">
          <span v-if="summary.verification_mode === 'ASN_ONLY'">No Pack List is attached. Scans will be recorded as unverified physical receipt.</span>
          <span v-else-if="summary.verification_mode === 'PACK_LIST_QTY'">Pack List quantities are attached, but it has no SN. Physical scans are recorded without SN matching.</span>
          <span v-else-if="summary.verification_mode === 'PACK_LIST_PENDING'">Pack List SN is pending confirmation. Confirm the document before using it as the receiving baseline.</span>
          <span v-else>{{ summary.ready_for_putaway ? 'SN check passed. Putaway is allowed.' : 'SN check is incomplete. Resolve missing or exception SN before putaway.' }}<span v-if="summary.total_resolved_exceptions"> Resolved exceptions: {{ summary.total_resolved_exceptions }}.</span></span>
        </q-banner>

        <q-separator />
        <div class="text-subtitle2">Expected SN</div>
        <div class="row q-col-gutter-sm">
          <div class="col-12 col-md-7">
            <q-input
              v-model="expectedText"
              outlined
              type="textarea"
              autogrow
              label="One expected SN per line"
            />
          </div>
          <div class="col-12 col-md-5 q-gutter-y-sm">
            <q-btn color="primary" label="Save Expected SN" @click="saveExpectedText" />
            <q-file v-model="selectedFile" outlined dense accept=".xlsx" label="Scan sheet (.xlsx)" />
            <q-input v-model="inboundPo" outlined dense label="Inbound PO filter" />
            <q-input v-model="shipoutRef" outlined dense label="IB / SHIPOUT filter" />
            <div class="q-gutter-xs">
              <q-btn outline color="primary" label="Import Expected Excel" @click="importFile('expected')" />
              <q-btn outline color="positive" label="Import Received Excel" @click="importFile('receive')" />
            </div>
          </div>
        </div>

        <q-separator />
        <div class="text-subtitle2">Receive Scan</div>
        <div class="row q-col-gutter-sm items-center">
          <div class="col-12 col-md-6">
            <q-input
              ref="scanInput"
              v-model="scanSerial"
              outlined
              dense
              autofocus
              label="Scan SN and press Enter"
              @keyup.enter="scanCurrent"
            />
          </div>
          <div class="col-6 col-md-2"><q-checkbox v-model="scanDamaged" label="Damaged" /></div>
          <div class="col-6 col-md-2"><q-btn color="positive" label="Receive Scan" @click="scanCurrent" /></div>
        </div>

        <q-table
          dense
          flat
          bordered
          row-key="id"
          :data="records"
          :columns="recordColumns"
          :pagination.sync="pagination"
          no-data-label="No SN records"
        >
          <template v-slot:body-cell-resolution="props">
            <q-btn
              v-if="canResolve(props.row)"
              dense
              flat
              color="primary"
              :label="props.row.exception_resolved ? 'Reopen' : 'Resolve'"
              @click="openSerialResolution(props.row)"
            />
            <span v-else class="text-grey-6">-</span>
          </template>
        </q-table>

        <q-dialog v-model="resolutionForm">
          <q-card style="width: 460px; max-width: 92vw">
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
                label="Resolution"
              />
              <q-input
                v-model="resolutionNote"
                outlined
                type="textarea"
                autogrow
                label="Audit note"
                hint="Required when accepting an exception"
              />
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat label="Cancel" v-close-popup />
              <q-btn color="primary" label="Save" @click="submitResolution" />
            </q-card-actions>
          </q-card>
        </q-dialog>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script>
import { getauth, postauth, postauthfile } from '../boot/axios_request'

export default {
  name: 'AsnSerialPanel',
  props: {
    value: { type: Boolean, default: false },
    asnCode: { type: String, default: '' },
    goodsCode: { type: String, default: '' }
  },
  data () {
    return {
      details: [],
      selectedGoodsCode: this.goodsCode,
      summary: null,
      records: [],
      expectedText: '',
      scanSerial: '',
      scanDamaged: false,
      selectedFile: null,
      inboundPo: '',
      shipoutRef: '',
      pagination: { page: 1, rowsPerPage: 10 },
      resolutionForm: false,
      resolutionType: '',
      resolutionTarget: null,
      resolutionAction: '',
      resolutionNote: '',
      recordColumns: [
        { name: 'serial_number', label: 'SN', field: 'serial_number', align: 'left' },
        { name: 'goods_code', label: 'SKU', field: 'goods_code', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'scan_count', label: 'Scans', field: 'scan_count', align: 'center' },
        { name: 'inbound_po', label: 'PO', field: 'inbound_po', align: 'left' },
        { name: 'shipout_ref', label: 'IB', field: 'shipout_ref', align: 'left' },
        { name: 'source_location', label: 'Source Location', field: 'source_location', align: 'left' },
        { name: 'resolution', label: 'Resolution', field: 'exception_resolved', align: 'center' }
      ]
    }
  },
  computed: {
    goodsOptions () {
      return this.details.map(item => ({ label: item.goods_code, value: item.goods_code }))
    },
    selectedLine () {
      if (!this.summary || !this.selectedGoodsCode) return {}
      return this.summary.lines.find(item => item.goods_code === this.selectedGoodsCode) || {}
    },
    selectedDetail () {
      return this.details.find(item => item.goods_code === this.selectedGoodsCode) || {}
    },
    quantityExceptionQty () {
      const detail = this.selectedDetail
      return Number(detail.goods_shortage_qty || 0) + Number(detail.goods_more_qty || 0) + Number(detail.goods_damage_qty || 0)
    },
    quantityExceptionLabel () {
      const detail = this.selectedDetail
      const parts = []
      if (detail.goods_shortage_qty) parts.push('Shortage ' + detail.goods_shortage_qty)
      if (detail.goods_more_qty) parts.push('Overage ' + detail.goods_more_qty)
      if (detail.goods_damage_qty) parts.push('Damage ' + detail.goods_damage_qty)
      return 'Quantity: ' + parts.join(' / ') + (detail.exception_resolved ? ' (resolved)' : '')
    },
    resolutionTitle () {
      return this.resolutionType === 'quantity' ? 'Quantity exception' : 'Serial exception'
    },
    resolutionActionOptions () {
      if (this.resolutionType === 'quantity') {
        return [
          { label: 'Accept exception', value: 'ACCEPT_EXCEPTION' },
          { label: 'Reopen', value: 'REOPEN' }
        ]
      }
      return this.resolutionTarget && this.resolutionTarget.is_received
        ? [
          { label: 'Accept exception', value: 'ACCEPT_EXCEPTION' },
          { label: 'Reopen', value: 'REOPEN' }
        ]
        : [
          { label: 'Waive missing SN', value: 'WAIVE_MISSING' },
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
      getauth('asn/detail/?asn_code=' + encodeURIComponent(this.asnCode)).then(res => {
        this.details = res.results || []
        if (!this.selectedGoodsCode && this.details.length) this.selectedGoodsCode = this.details[0].goods_code
        return this.refreshSerialData()
      }).catch(() => {})
    },
    refreshSerialData () {
      const query = '?asn_code=' + encodeURIComponent(this.asnCode)
      return getauth('asn/serial/summary/' + query).then(res => {
        this.summary = res
        return getauth('asn/serial/records/' + query + (this.selectedGoodsCode ? '&goods_code=' + encodeURIComponent(this.selectedGoodsCode) : ''))
      }).then(res => {
        this.records = res.results || []
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to load SN data', color: 'negative' })
      })
    },
    canResolve (record) {
      return Boolean(record.exception_resolved || record.status === 'UNEXPECTED' || record.status === 'DUPLICATE' || record.status === 'WRONG_SKU' || record.status === 'DAMAGED' || record.status === 'REJECTED' || (record.is_expected && !record.is_received))
    },
    openSerialResolution (record) {
      this.resolutionType = 'serial'
      this.resolutionTarget = record
      this.resolutionAction = record.exception_resolved ? 'REOPEN' : (record.is_received ? 'ACCEPT_EXCEPTION' : 'WAIVE_MISSING')
      this.resolutionNote = record.exception_resolution_note || ''
      this.resolutionForm = true
    },
    openQuantityResolution () {
      this.resolutionType = 'quantity'
      this.resolutionTarget = this.selectedDetail
      this.resolutionAction = this.selectedDetail.exception_resolved ? 'REOPEN' : 'ACCEPT_EXCEPTION'
      this.resolutionNote = this.selectedDetail.exception_resolution_note || ''
      this.resolutionForm = true
    },
    submitResolution () {
      if (!this.resolutionTarget) return
      const isQuantity = this.resolutionType === 'quantity'
      const payload = isQuantity
        ? {
          asn_code: this.asnCode,
          goods_code: this.resolutionTarget.goods_code,
          action: this.resolutionAction,
          note: this.resolutionNote
        }
        : {
          id: this.resolutionTarget.id,
          action: this.resolutionAction,
          note: this.resolutionNote
        }
      const endpoint = isQuantity ? 'asn/serial/exceptions/resolve-quantity/' : 'asn/serial/exceptions/resolve/'
      postauth(endpoint, payload).then(() => {
        this.resolutionForm = false
        this.refreshSerialData()
        this.$q.notify({ message: 'Exception status updated', color: 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to update exception', color: 'negative' })
      })
    },
    saveExpectedText () {
      const serialNumbers = this.expectedText.split(/\r?\n/).map(value => value.trim()).filter(Boolean)
      if (!this.selectedGoodsCode || !serialNumbers.length) {
        this.$q.notify({ message: 'Select SKU and enter expected SN', color: 'negative' })
        return
      }
      postauth('asn/serial/expected/', {
        asn_code: this.asnCode,
        goods_code: this.selectedGoodsCode,
        serial_numbers: serialNumbers
      }).then(() => {
        this.expectedText = ''
        this.refreshSerialData()
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to save expected SN', color: 'negative' })
      })
    },
    scanCurrent () {
      if (!this.scanSerial || !this.selectedGoodsCode) return
      postauth('asn/serial/scan/', {
        asn_code: this.asnCode,
        goods_code: this.selectedGoodsCode,
        serial_number: this.scanSerial,
        damaged: this.scanDamaged
      }).then(res => {
        this.scanSerial = ''
        this.scanDamaged = false
        this.refreshSerialData()
        if (res.record && res.record.status !== 'ACCEPTED') {
          this.$q.notify({ message: 'SN result: ' + res.record.status, color: 'warning' })
        }
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to record scan', color: 'negative' })
      })
    },
    importFile (mode) {
      if (!this.selectedFile || (!this.inboundPo && !this.shipoutRef)) {
        this.$q.notify({ message: 'Select an Excel file and provide PO or IB filter', color: 'negative' })
        return
      }
      const form = new FormData()
      form.append('file', this.selectedFile)
      form.append('asn_code', this.asnCode)
      form.append('mode', mode)
      form.append('inbound_po', this.inboundPo)
      form.append('shipout_ref', this.shipoutRef)
      postauthfile('asn/serial/import/', form).then(res => {
        this.refreshSerialData()
        this.$q.notify({ message: 'Imported ' + res.matched_rows + ' rows', color: res.errors && res.errors.length ? 'warning' : 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to import scan sheet', color: 'negative' })
      })
    }
  }
}
</script>
