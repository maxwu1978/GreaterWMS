<template>
  <div class="q-pa-sm">
    <div class="row q-col-gutter-sm">
      <div class="col-12 col-lg-7">
        <q-card flat bordered class="full-height">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle2">Customer Pack List</div>
            <div class="text-caption text-grey-7">Reference data. It may arrive before or after the goods.</div>
          </q-card-section>
          <q-card-section class="row q-col-gutter-sm items-center q-pt-xs">
            <div class="col-12 col-md-5">
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
            <div class="col-12 col-md-7">
              <q-file v-model="selectedFile" outlined dense accept=".xlsx" label="Customer Pack List (.xlsx)" />
            </div>
            <div class="col-12 col-md-4">
              <q-select v-model="sourceType" outlined dense emit-value map-options :options="sourceTypes" label="Source" />
            </div>
            <div class="col-12 col-md-4">
              <q-input v-model.number="packageQty" outlined dense type="number" min="0" label="Load units" />
            </div>
            <div class="col-12 col-md-4 text-right">
              <q-btn color="primary" icon="preview" label="Preview" :disable="!asnCode || !selectedFile" @click="previewFile" />
            </div>
            <div class="col-12">
              <q-input v-model="note" outlined dense label="Note" />
            </div>
          </q-card-section>
        </q-card>
      </div>
      <div class="col-12 col-lg-5">
        <q-card flat bordered class="full-height">
          <q-card-section class="q-pb-xs">
            <div class="text-subtitle2">QC Inspection</div>
            <div class="text-caption text-grey-7">Import the operator's inspection workbook. Each import is a separate QC round.</div>
          </q-card-section>
          <q-card-section class="row q-col-gutter-sm items-center q-pt-xs">
            <div class="col-12">
              <q-file v-model="inspectionFile" outlined dense accept=".xlsx" label="QC Inspection Workbook (.xlsx)" />
            </div>
            <div class="col-12 col-md-5">
              <q-select v-model="inspectionSourceType" outlined dense emit-value map-options :options="sourceTypes" label="Source" />
            </div>
            <div class="col-12 col-md-7 text-right">
              <q-btn color="secondary" icon="fact_check" label="Import QC Results" :disable="!asnCode || !inspectionFile" @click="importInspection" />
            </div>
            <div class="col-12">
              <q-input v-model="inspectionNote" outlined dense label="QC note" />
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <q-banner v-if="summary" class="q-mt-sm" :class="summary.reconciliation_status === 'EXCEPTION' ? 'bg-red-1' : (summary.reconciliation_status === 'PASSED' ? 'bg-green-1' : 'bg-orange-1')">
      <div class="row items-center q-col-gutter-md">
        <div class="col-12 col-md-4">
          <div class="text-subtitle2">Receiving Reconciliation</div>
          <div class="text-caption">{{ summary.customer_short_name || summary.customer || '-' }} · {{ asnCode }}</div>
        </div>
        <div class="col-6 col-md-2"><q-chip dense :color="statusColor(summary.reconciliation_status)">{{ statusLabel(summary.reconciliation_status) }}</q-chip></div>
        <div class="col-6 col-md-2 text-caption">Pack List: <strong>{{ packListLabel(summary.pack_list_status) }}</strong></div>
        <div class="col-6 col-md-2 text-caption">QC: <strong>{{ summary.qc_status || 'NOT_STARTED' }}</strong></div>
        <div class="col-6 col-md-2 text-caption">Customer SN: <strong>{{ summary.customer_sn_status || 'NOT_PROVIDED' }}</strong></div>
        <div class="col-6 col-md-2 text-caption">ETA: <strong>{{ etaLabel }}</strong></div>
      </div>
      <div v-if="summary.receiving_summary" class="text-caption q-mt-xs">
        Receiving: {{ summary.receiving_summary.scanned || 0 }} scanned / {{ summary.receiving_summary.accepted || 0 }} accepted · Open exceptions: {{ summary.receiving_summary.open_exceptions || 0 }} · Resolved: {{ summary.receiving_summary.resolved_exceptions || 0 }}
      </div>
      <div v-if="summary.pack_list_status === 'PENDING' || summary.pack_list_status === 'LATE_PENDING'" class="text-caption text-orange-10 q-mt-xs">Confirm the customer Pack List before using it as the receiving baseline.</div>
      <div v-if="summary.pack_list_timing === 'LATE_REFERENCE'" class="text-caption text-blue-10 q-mt-xs">This Pack List was received after physical receiving started and is stored as a late reference revision.</div>
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
          <q-btn v-if="props.row.is_current && props.row.status !== 'CONFIRMED'" dense flat color="positive" icon="check" label="Confirm" @click="confirmDocument(props.row)" />
          <q-btn dense flat color="info" icon="visibility" @click="showDocument(props.row)" />
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
      <template v-slot:body-cell-status="props">
        <q-td :props="props"><q-chip dense :color="inspectionColor(props.value)">{{ props.value }}</q-chip></q-td>
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
          <div class="text-caption q-mb-sm">The uploaded file is not stored. Only the parsed Pack List content is saved.</div>
          <div class="row q-col-gutter-md text-caption q-mb-sm">
            <div class="col-6 col-md-2">ASN: {{ previewData.asn_code }}</div>
            <div class="col-6 col-md-2">Rows: {{ previewData.row_count }}</div>
            <div class="col-6 col-md-2">Qty: {{ previewData.total_qty }}</div>
            <div class="col-6 col-md-2">SN: {{ previewData.expected_serial_count }}</div>
            <div class="col-6 col-md-2">Packages: {{ previewData.package_qty || 'Not provided' }}</div>
            <div class="col-6 col-md-2">File: {{ previewData.status }}</div>
          </div>
          <q-banner v-if="previewData.duplicate_document" class="bg-green-1 q-mb-sm">
            The same Pack List content is already current for this ASN. No second record will be created.
          </q-banner>
          <q-banner v-else-if="previewData.replace_required" class="bg-orange-1 q-mb-sm">
            A different Pack List is already current for this ASN. Importing will explicitly replace its current content and keep the old rows as history.
          </q-banner>
          <q-banner v-if="previewData.late_reference_required" class="bg-blue-1 q-mb-sm">
            Receiving has already started. This import will be stored as a late reference revision and will not overwrite the prior receiving history.
          </q-banner>
          <q-list bordered separator style="max-height: 420px; overflow-y: auto">
            <q-item v-for="(line, index) in previewData.lines" :key="index">
                <q-item-section>
                  <q-item-label>{{ line.goods_code }} · {{ line.goods_qty }}</q-item-label>
                  <q-item-label caption v-if="line.customer_goods_code">Customer SKU: {{ line.customer_goods_code }}</q-item-label>
                  <q-item-label caption v-if="line.customer_ssku">Customer S-SKU: {{ line.customer_ssku }}</q-item-label>
                  <q-item-label caption v-if="line.package_type">Package: {{ line.package_type }}</q-item-label>
                  <q-item-label caption v-if="line.serial_number">SN: {{ line.serial_number }}</q-item-label>
              </q-item-section>
              <q-item-section side>{{ line.goods_desc }}</q-item-section>
            </q-item>
          </q-list>
          <div class="text-right q-mt-md">
            <q-btn flat label="Cancel" v-close-popup />
            <q-btn color="primary" :label="previewData.duplicate_document ? 'Use Existing Pack List' : (previewData.replace_required ? 'Replace Current Pack List' : 'Import as Pending')" @click="importFile" />
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

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

    <asn-serial-panel
      v-model="serialPanelOpen"
      :asn-code="asnCode"
      :goods-code="selectedReconciliation ? selectedReconciliation.goods_code : ''"
    />
  </div>
</template>

<script>
import { getauth, postauth, postauthfile } from 'boot/axios_request'
import AsnSerialPanel from '../../components/AsnSerialPanel.vue'

export default {
  name: 'Pagepacklist',
  components: {
    AsnSerialPanel
  },
  data () {
    return {
      asnCode: this.$route.query.asn_code || '',
      asnOptions: [],
      documents: [],
      inspectionBatches: [],
      summary: null,
      selectedFile: null,
      inspectionFile: null,
      sourceType: 'UPLOAD',
      inspectionSourceType: 'UPLOAD',
      note: '',
      inspectionNote: '',
      packageQty: 0,
      previewOpen: false,
      previewData: null,
      loading: false,
      detailOpen: false,
      selectedDocument: null,
      serialPanelOpen: false,
      selectedReconciliation: null,
      sourceTypes: [
        { label: 'Upload', value: 'UPLOAD' },
        { label: 'Email', value: 'EMAIL' },
        { label: 'Google Drive', value: 'GOOGLE_DRIVE' },
        { label: 'Manual', value: 'MANUAL' }
      ],
      columns: [
        { name: 'version', label: 'Revision', field: 'version', align: 'center' },
        { name: 'asn_code', label: 'ASN', field: 'asn_code', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'timing', label: 'Timing', field: 'late_reference', align: 'center' },
        { name: 'line_count', label: 'Lines', field: 'line_count', align: 'center' },
        { name: 'total_qty', label: 'Qty', field: 'total_qty', align: 'center' },
        { name: 'package_qty', label: 'Load Units', field: 'package_qty', align: 'center' },
        { name: 'expected_serial_count', label: 'SN', field: 'expected_serial_count', align: 'center' },
        { name: 'action', label: 'Action', align: 'right' }
      ],
      inspectionColumns: [
        { name: 'id', label: 'Round', field: 'id', align: 'center' },
        { name: 'created_at', label: 'Imported', field: 'created_at', align: 'left' },
        { name: 'status', label: 'Status', field: 'status', align: 'center' },
        { name: 'matched_count', label: 'Rows', field: 'matched_count', align: 'center' },
        { name: 'accepted_count', label: 'Accepted', field: 'accepted_count', align: 'center' },
        { name: 'exception_count', label: 'Exceptions', field: 'exception_count', align: 'center' },
        { name: 'source_type', label: 'Source', field: 'source_type', align: 'center' }
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
    packListForm () {
      const form = new FormData()
      form.append('file', this.selectedFile)
      form.append('asn_code', this.asnCode)
      form.append('source_type', this.sourceType)
      form.append('note', this.note)
      form.append('package_qty', this.packageQty || 0)
      if (this.previewData && this.previewData.replace_required) form.append('replace', 'true')
      if (this.previewData && this.previewData.late_reference_required) form.append('late_reference', 'true')
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
        this.$q.notify({ message: res.duplicate ? 'Existing Pack List reused.' : (res.replaced ? 'Pack List replaced. Confirm it before receiving.' : 'Pack List imported. Confirm it before receiving.'), color: 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to import Pack List', color: 'negative' })
      })
    },
    importInspection () {
      const form = new FormData()
      form.append('file', this.inspectionFile)
      form.append('asn_code', this.asnCode)
      form.append('mode', 'receive')
      form.append('allow_all', 'true')
      form.append('source_type', this.inspectionSourceType)
      form.append('note', this.inspectionNote)
      postauthfile('asn/serial/inspections/import/', form).then(res => {
        this.inspectionFile = null
        this.inspectionNote = ''
        this.loadDocuments()
        this.$q.notify({ message: res.duplicate ? 'This QC workbook was already imported.' : 'QC inspection imported.', color: res.summary && res.summary.qc_status === 'EXCEPTION' ? 'warning' : 'positive' })
      }).catch(err => {
        this.$q.notify({ message: err.detail || 'Unable to import QC inspection', color: 'negative' })
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
    },
    showReconciliation (row) {
      this.selectedReconciliation = row
      this.serialPanelOpen = true
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
.reconciliation-table .ellipsis-cell {
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
