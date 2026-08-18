<template>
  <q-page class="source-intake-page q-pa-md">
    <q-card flat bordered class="source-intake-card">
      <q-card-section class="row items-center q-pb-sm">
        <div>
          <div class="text-h5 text-weight-bold">Source Intake</div>
          <div class="text-caption text-grey-7">Email evidence and AI processing status</div>
        </div>
        <q-space />
        <q-btn flat round icon="refresh" :loading="loading" aria-label="Refresh" @click="load" />
      </q-card-section>

      <q-separator />

      <q-card-section class="row items-center q-col-gutter-sm q-py-sm">
        <div class="col-12 col-sm-4 col-md-3">
          <q-select v-model="status" dense outlined clearable emit-value map-options :options="statusOptions" label="Status" @input="load" />
        </div>
        <div class="col-12 col-sm-4 col-md-3">
          <q-select v-model="operation" dense outlined clearable emit-value map-options :options="operationOptions" label="Operation" @input="load" />
        </div>
        <div class="col-12 col-sm-4 col-md-4">
          <q-input v-model="search" dense outlined clearable label="Search" @keyup.enter="load" />
        </div>
        <div class="col-auto">
          <q-btn color="primary" unelevated label="Search" :loading="loading" @click="load" />
        </div>
      </q-card-section>

      <q-card-section class="source-intake-counts row q-gutter-sm q-py-none">
        <q-chip v-for="item in countItems" :key="item.key" dense square :color="item.color" text-color="white">
          {{ item.label }} {{ counts[item.key] || 0 }}
        </q-chip>
      </q-card-section>

      <q-table
        class="source-intake-table"
        :data="rows"
        :columns="columns"
        row-key="id"
        dense
        flat
        bordered
        separator="horizontal"
        :loading="loading"
        :pagination.sync="pagination"
        :rows-per-page-options="[0]"
        no-data-label="No source records"
      >
        <template v-slot:body-cell-received_at="props">
          <q-td :props="props">{{ formatDate(props.row.received_at || props.row.captured_at) }}</q-td>
        </template>
        <template v-slot:body-cell-source="props">
          <q-td :props="props">
            <div class="text-weight-medium">{{ props.row.document_type || 'OTHER' }}</div>
            <div class="text-caption text-grey-7">{{ props.row.sender_email || props.row.mailbox_account || '-' }}</div>
          </q-td>
        </template>
        <template v-slot:body-cell-status="props">
          <q-td :props="props"><q-badge :color="statusColor(props.row.status)">{{ props.row.status }}</q-badge></q-td>
        </template>
        <template v-slot:body-cell-reference="props">
          <q-td :props="props">
            <div>{{ props.row.external_reference || props.row.matched_entity_ref || '-' }}</div>
            <div class="text-caption text-grey-7 ellipsis" :title="props.row.subject">{{ props.row.subject || '-' }}</div>
          </q-td>
        </template>
        <template v-slot:body-cell-next_action="props">
          <q-td :props="props" class="source-intake-next">{{ props.row.next_action || props.row.exception_summary || '-' }}</q-td>
        </template>
        <template v-slot:body-cell-action="props">
          <q-td :props="props"><q-btn flat dense color="primary" icon="open_in_new" aria-label="Open" @click="showDetail(props.row.id)" /></q-td>
        </template>
      </q-table>

      <q-card-actions align="right" v-if="hasMore" class="q-pa-sm">
        <q-btn flat color="primary" label="Load more" :loading="loading" @click="loadMore" />
      </q-card-actions>
    </q-card>

    <q-dialog v-model="detailOpen" position="right">
      <q-card class="source-intake-detail">
        <q-card-section class="row items-center q-pb-sm">
          <div class="text-h6">Source Record {{ detail ? detail.id : '' }}</div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup aria-label="Close" />
        </q-card-section>
        <q-separator />
        <q-card-section v-if="detail">
          <div class="source-intake-detail-grid">
            <div><span>Status</span><strong>{{ detail.status }}</strong></div>
            <div><span>Operation</span><strong>{{ detail.operation }}</strong></div>
            <div><span>Document</span><strong>{{ detail.document_type }}</strong></div>
            <div><span>Reference</span><strong>{{ detail.external_reference || '-' }}</strong></div>
            <div><span>Sender</span><strong>{{ detail.sender_email || '-' }}</strong></div>
            <div><span>Mailbox</span><strong>{{ detail.mailbox_account || '-' }}</strong></div>
          </div>
          <q-separator class="q-my-md" />
          <div class="text-caption text-grey-7">Subject</div>
          <div class="q-mb-md">{{ detail.subject || '-' }}</div>
          <div class="text-caption text-grey-7">Next step</div>
          <div class="q-mb-md">{{ detail.next_action || '-' }}</div>
          <div v-if="detail.exception_summary" class="source-intake-exception q-pa-sm q-mb-md">
            {{ detail.exception_summary }}
          </div>
          <div class="text-subtitle2 q-mb-sm">Attachments</div>
          <div v-if="detail.attachments && detail.attachments.length">
            <div v-for="attachment in detail.attachments" :key="attachment.id" class="source-intake-attachment q-pa-sm q-mb-xs">
              <div>{{ attachment.attachment_name }}</div>
              <div class="text-caption text-grey-7">{{ attachment.content_type || 'file' }} · {{ attachment.security_status }}</div>
            </div>
          </div>
          <div v-else class="text-caption text-grey-7">No attachment metadata</div>
          <div class="text-subtitle2 q-mt-md q-mb-sm">Processing events</div>
          <q-timeline color="primary" layout="dense">
            <q-timeline-entry v-for="event in (detail.events || [])" :key="event.id" :title="event.event_type" :subtitle="formatDate(event.created_at)">
              {{ event.message || event.status }}
            </q-timeline-entry>
          </q-timeline>
        </q-card-section>
        <q-card-section v-else class="text-grey-7">No source record selected.</q-card-section>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'SourceIntake',
  data () {
    return {
      loading: false,
      rows: [],
      detail: null,
      detailOpen: false,
      status: '',
      operation: '',
      search: '',
      counts: {},
      hasMore: false,
      pagination: { rowsPerPage: 0 },
      offset: 0,
      statusOptions: [
        { label: 'Review required', value: 'REVIEW_REQUIRED' },
        { label: 'Approval required', value: 'APPROVAL_REQUIRED' },
        { label: 'Ready for preview', value: 'READY_FOR_PREVIEW' },
        { label: 'Blocked', value: 'BLOCKED' },
        { label: 'Completed', value: 'COMPLETED' },
        { label: 'Duplicate', value: 'DUPLICATE' },
        { label: 'Failed', value: 'FAILED' }
      ],
      operationOptions: [
        { label: 'Inbound', value: 'INBOUND' },
        { label: 'Outbound', value: 'OUTBOUND' },
        { label: 'Supporting', value: 'SUPPORTING' },
        { label: 'Unknown', value: 'UNKNOWN' }
      ],
      columns: [
        { name: 'received_at', label: 'Received', field: 'received_at', align: 'left', style: 'width: 130px' },
        { name: 'source', label: 'Source', field: 'document_type', align: 'left', style: 'width: 210px' },
        { name: 'operation', label: 'Operation', field: 'operation', align: 'left', style: 'width: 100px' },
        { name: 'reference', label: 'Reference', field: 'external_reference', align: 'left', style: 'width: 190px' },
        { name: 'status', label: 'Status', field: 'status', align: 'left', style: 'width: 150px' },
        { name: 'next_action', label: 'Next step', field: 'next_action', align: 'left' },
        { name: 'action', label: '', field: 'action', align: 'right', style: 'width: 48px' }
      ]
    }
  },
  computed: {
    countItems () {
      return [
        { key: 'REVIEW_REQUIRED', label: 'Review', color: 'orange-8' },
        { key: 'APPROVAL_REQUIRED', label: 'Approval', color: 'blue-8' },
        { key: 'BLOCKED', label: 'Blocked', color: 'negative' },
        { key: 'COMPLETED', label: 'Completed', color: 'positive' }
      ]
    }
  },
  mounted () {
    this.load()
  },
  methods: {
    queryString (offset) {
      const params = new URLSearchParams()
      params.set('limit', '50')
      params.set('offset', String(offset))
      if (this.status) params.set('status', this.status)
      if (this.operation) params.set('operation', this.operation)
      if (this.search) params.set('q', this.search)
      return `asn/serial/intake/?${params.toString()}`
    },
    load () {
      this.loading = true
      this.offset = 0
      getauth(this.queryString(0))
        .then(res => {
          this.rows = res.items || []
          this.counts = res.counts || {}
          this.hasMore = Boolean(res.has_more)
        })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    loadMore () {
      this.loading = true
      const nextOffset = this.rows.length
      getauth(this.queryString(nextOffset))
        .then(res => {
          this.rows = this.rows.concat(res.items || [])
          this.counts = res.counts || this.counts
          this.hasMore = Boolean(res.has_more)
          this.offset = nextOffset
        })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    showDetail (id) {
      this.detailOpen = true
      this.detail = null
      getauth(`asn/serial/intake/${id}/`).then(res => { this.detail = res }).catch(() => {})
    },
    formatDate (value) {
      return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
    },
    statusColor (value) {
      return {
        REVIEW_REQUIRED: 'orange-8',
        APPROVAL_REQUIRED: 'blue-8',
        READY_FOR_PREVIEW: 'teal-7',
        BLOCKED: 'negative',
        FAILED: 'negative',
        COMPLETED: 'positive',
        DUPLICATE: 'grey-7'
      }[value] || 'grey-7'
    }
  }
}
</script>

<style scoped>
.source-intake-page {
  background: #f4f6f8;
}

.source-intake-card {
  width: 100%;
}

.source-intake-table {
  margin-top: 12px;
}

.source-intake-next {
  min-width: 220px;
  white-space: normal;
}

.source-intake-detail {
  width: min(520px, 100vw);
  max-width: 100vw;
  min-height: 100vh;
}

.source-intake-detail-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.source-intake-detail-grid span {
  color: #78909c;
  display: block;
  font-size: 11px;
  text-transform: uppercase;
}

.source-intake-detail-grid strong {
  display: block;
  overflow-wrap: anywhere;
}

.source-intake-exception {
  background: #fff3e0;
  color: #8d4a00;
}

.source-intake-attachment {
  background: #f5f7f9;
  border: 1px solid #e0e6ea;
}
</style>
