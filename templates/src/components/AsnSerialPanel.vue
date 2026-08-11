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
        </div>

        <q-banner v-if="summary" :class="summary.ready_for_putaway ? 'bg-green-1' : 'bg-orange-1'">
          <span v-if="summary.verification_mode === 'ASN_ONLY'">No Pack List is attached. Scans will be recorded as unverified physical receipt.</span>
          <span v-else-if="summary.verification_mode === 'PACK_LIST_QTY'">Pack List quantities are attached, but it has no SN. Physical scans are recorded without SN matching.</span>
          <span v-else-if="summary.verification_mode === 'PACK_LIST_PENDING'">Pack List SN is pending confirmation. Confirm the document before using it as the receiving baseline.</span>
          <span v-else>{{ summary.ready_for_putaway ? 'SN check passed. Putaway is allowed.' : 'SN check is incomplete. Resolve missing or exception SN before putaway.' }}</span>
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
        />
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
      recordColumns: [
        { name: 'serial_number', label: 'SN', field: 'serial_number', align: 'left' },
        { name: 'goods_code', label: 'SKU', field: 'goods_code', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'scan_count', label: 'Scans', field: 'scan_count', align: 'center' },
        { name: 'inbound_po', label: 'PO', field: 'inbound_po', align: 'left' },
        { name: 'shipout_ref', label: 'IB', field: 'shipout_ref', align: 'left' },
        { name: 'source_location', label: 'Source Location', field: 'source_location', align: 'left' }
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
      if (!this.selectedFile || !this.inboundPo && !this.shipoutRef) {
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
