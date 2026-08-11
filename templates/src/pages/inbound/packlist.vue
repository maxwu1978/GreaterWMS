<template>
  <div class="q-pa-sm">
    <q-card flat bordered>
      <q-card-section class="row q-col-gutter-sm items-center">
        <div class="col-12 col-md-4">
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
        <div class="col-12 col-md-3">
          <q-file v-model="selectedFile" outlined dense accept=".xlsx" label="Pack List (.xlsx)" />
        </div>
        <div class="col-12 col-md-2">
          <q-select
            v-model="sourceType"
            outlined
            dense
            emit-value
            map-options
            :options="sourceTypes"
            label="Source"
          />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="sourceUrl" outlined dense label="Source link (optional)" />
        </div>
        <div class="col-12 col-md-9">
          <q-input v-model="note" outlined dense label="Note" />
        </div>
        <div class="col-12 col-md-3 text-right">
          <q-btn color="primary" icon="file_upload" label="Import Pack List" :disable="!asnCode || !selectedFile" @click="importFile" />
        </div>
      </q-card-section>
    </q-card>

    <q-banner v-if="summary" class="q-mt-sm" :class="summary.ready_for_putaway ? 'bg-green-1' : 'bg-orange-1'">
      <div class="text-subtitle2">{{ summary.verification_mode }}</div>
      <div class="text-caption">{{ summary.verification_note }}</div>
      <div class="text-caption">Pack List: {{ summary.pack_list_present ? 'present' : 'not received' }} · SN: {{ summary.total_expected_serials || 0 }} expected / {{ summary.total_received_serials || 0 }} received</div>
    </q-banner>

    <q-table
      class="q-mt-sm my-sticky-header-table shadow-24"
      flat
      bordered
      dense
      row-key="id"
      :data="documents"
      :columns="columns"
      :loading="loading"
      no-data-label="No Pack List"
    >
      <template v-slot:body-cell-status="props">
        <q-td :props="props">
          <q-chip dense :color="props.value === 'CONFIRMED' ? 'positive' : 'orange-3'">{{ props.value }}</q-chip>
        </q-td>
      </template>
      <template v-slot:body-cell-action="props">
        <q-td :props="props">
          <q-btn v-if="props.row.status !== 'CONFIRMED'" dense flat color="positive" icon="check" label="Confirm" @click="confirmDocument(props.row)" />
          <q-btn dense flat color="info" icon="visibility" @click="showDocument(props.row)" />
        </q-td>
      </template>
    </q-table>

    <q-dialog v-model="detailOpen">
      <q-card style="width: 900px; max-width: 95vw">
        <q-bar class="bg-light-blue-10 text-white">
          <div>{{ selectedDocument ? selectedDocument.asn_code + ' / Pack List v' + selectedDocument.version : 'Pack List' }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section v-if="selectedDocument">
          <div class="row q-col-gutter-md text-caption q-mb-sm">
            <div class="col-6 col-md-3">Status: {{ selectedDocument.status }}</div>
            <div class="col-6 col-md-3">Lines: {{ selectedDocument.line_count }}</div>
            <div class="col-6 col-md-3">Qty: {{ selectedDocument.total_qty }}</div>
            <div class="col-6 col-md-3">SN: {{ selectedDocument.expected_serial_count }}</div>
          </div>
          <q-list bordered separator>
            <q-item v-for="(line, index) in selectedDocument.lines" :key="index">
              <q-item-section>
                <q-item-label>{{ line.goods_code }}</q-item-label>
                <q-item-label caption v-if="line.customer_goods_code">Customer SKU: {{ line.customer_goods_code }}</q-item-label>
              </q-item-section>
              <q-item-section side>{{ line.goods_qty }}</q-item-section>
            </q-item>
          </q-list>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { getauth, postauth, postauthfile } from 'boot/axios_request'

export default {
  name: 'Pagepacklist',
  data () {
    return {
      asnCode: this.$route.query.asn_code || '',
      asnOptions: [],
      documents: [],
      summary: null,
      selectedFile: null,
      sourceType: 'UPLOAD',
      sourceUrl: '',
      note: '',
      loading: false,
      detailOpen: false,
      selectedDocument: null,
      sourceTypes: [
        { label: 'Upload', value: 'UPLOAD' },
        { label: 'Email', value: 'EMAIL' },
        { label: 'Google Drive', value: 'GOOGLE_DRIVE' },
        { label: 'Manual', value: 'MANUAL' }
      ],
      columns: [
        { name: 'version', label: 'Version', field: 'version', align: 'center' },
        { name: 'asn_code', label: 'ASN', field: 'asn_code', align: 'left' },
        { name: 'source_file', label: 'File', field: 'source_file', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'line_count', label: 'Lines', field: 'line_count', align: 'center' },
        { name: 'total_qty', label: 'Qty', field: 'total_qty', align: 'center' },
        { name: 'expected_serial_count', label: 'SN', field: 'expected_serial_count', align: 'center' },
        { name: 'action', label: 'Action', align: 'right' }
      ]
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
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to load Pack List', color: 'negative' })
      }).then(() => {
        this.loading = false
      })
    },
    importFile () {
      const form = new FormData()
      form.append('file', this.selectedFile)
      form.append('asn_code', this.asnCode)
      form.append('source_type', this.sourceType)
      form.append('source_url', this.sourceUrl)
      form.append('note', this.note)
      postauthfile('asn/serial/packlists/import/', form).then(res => {
        this.selectedFile = null
        this.loadDocuments()
        this.$q.notify({ message: 'Pack List imported. Confirm it before receiving.', color: 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to import Pack List', color: 'negative' })
      })
    },
    confirmDocument (document) {
      this.$q.dialog({ title: 'Confirm Pack List', message: 'Use this Pack List for receiving verification?', cancel: true, persistent: true }).onOk(() => {
        postauth('asn/serial/packlists/confirm/', { id: document.id }).then(() => {
          this.loadDocuments()
          this.$q.notify({ message: 'Pack List confirmed', color: 'positive' })
        }).catch(err => {
          this.$q.notify({ message: err.detail || 'Unable to confirm Pack List', color: 'negative' })
        })
      })
    },
    showDocument (document) {
      this.selectedDocument = document
      this.detailOpen = true
    }
  }
}
</script>
