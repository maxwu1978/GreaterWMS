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
        <div class="col-12 col-md-2">
          <q-input v-model.number="packageQty" outlined dense type="number" min="0" label="Packages / load units" />
        </div>
        <div class="col-12 col-md-7">
          <q-input v-model="note" outlined dense label="Note" />
        </div>
        <div class="col-12 col-md-3 text-right">
          <q-btn color="primary" icon="preview" label="Preview Pack List" :disable="!asnCode || !selectedFile" @click="previewFile" />
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

    <q-dialog v-model="previewOpen">
      <q-card style="width: 1000px; max-width: 95vw">
        <q-bar class="bg-light-blue-10 text-white">
          <div>Pack List Preview</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section v-if="previewData">
          <div class="text-caption q-mb-sm">No data is saved until you confirm the import.</div>
          <div class="row q-col-gutter-md text-caption q-mb-sm">
            <div class="col-6 col-md-2">ASN: {{ previewData.asn_code }}</div>
            <div class="col-6 col-md-2">Rows: {{ previewData.row_count }}</div>
            <div class="col-6 col-md-2">Qty: {{ previewData.total_qty }}</div>
            <div class="col-6 col-md-2">SN: {{ previewData.expected_serial_count }}</div>
            <div class="col-6 col-md-2">Packages: {{ previewData.package_qty || 'Not provided' }}</div>
            <div class="col-6 col-md-2">File: {{ previewData.status }}</div>
          </div>
          <q-banner v-if="previewData.duplicate_document" class="bg-orange-1 q-mb-sm">
            This file was already imported for this ASN. The existing Pack List will be reused.
          </q-banner>
          <q-list bordered separator style="max-height: 420px; overflow-y: auto">
            <q-item v-for="(line, index) in previewData.lines" :key="index">
              <q-item-section>
                <q-item-label>{{ line.goods_code }} · {{ line.goods_qty }}</q-item-label>
                <q-item-label caption v-if="line.customer_goods_code">Customer SKU: {{ line.customer_goods_code }}</q-item-label>
                <q-item-label caption v-if="line.serial_number">SN: {{ line.serial_number }}</q-item-label>
              </q-item-section>
              <q-item-section side>{{ line.goods_desc }}</q-item-section>
            </q-item>
          </q-list>
          <div class="text-right q-mt-md">
            <q-btn flat label="Cancel" v-close-popup />
            <q-btn color="primary" :label="previewData.duplicate_document ? 'Use Existing Pack List' : 'Import as Pending'" @click="importFile" />
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

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
            <div class="col-6 col-md-3">Load units: {{ selectedDocument.package_qty || 'Not provided' }}</div>
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
      packageQty: 0,
      previewOpen: false,
      previewData: null,
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
        { name: 'package_qty', label: 'Load Units', field: 'package_qty', align: 'center' },
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
    packListForm () {
      const form = new FormData()
      form.append('file', this.selectedFile)
      form.append('asn_code', this.asnCode)
      form.append('source_type', this.sourceType)
      form.append('source_url', this.sourceUrl)
      form.append('note', this.note)
      form.append('package_qty', this.packageQty || 0)
      return form
    },
    previewFile () {
      postauthfile('asn/serial/packlists/preview/', this.packListForm()).then(res => {
        this.previewData = res.preview
        this.previewOpen = true
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to preview Pack List', color: 'negative' })
      })
    },
    importFile () {
      postauthfile('asn/serial/packlists/import/', this.packListForm()).then(res => {
        this.selectedFile = null
        this.previewOpen = false
        this.previewData = null
        this.loadDocuments()
        this.$q.notify({ message: res.duplicate ? 'Existing Pack List reused.' : 'Pack List imported. Confirm it before receiving.', color: 'positive' })
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
