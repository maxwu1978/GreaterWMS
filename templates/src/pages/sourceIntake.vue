<template>
  <q-page class="source-intake-page q-pa-md">
    <q-card flat bordered class="source-intake-card">
      <q-card-section class="row items-center q-pb-sm">
        <div>
          <div class="text-h6 text-weight-bold">Source Intake</div>
          <div class="text-caption text-grey-7">External instructions and email evidence</div>
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
          {{ item.label }} {{ item.value }}
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
          <q-td :props="props">
            <div class="text-weight-medium">{{ formatSourceTime(props.row.sent_at) }}</div>
            <div class="text-caption text-grey-7">Received {{ formatDate(props.row.received_at_raw || props.row.received_at || props.row.captured_at) }}</div>
          </q-td>
        </template>
        <template v-slot:body-cell-document="props">
          <q-td :props="props">
            <div class="text-weight-medium">{{ documentLabel(props.row.document_type) }}</div>
          </q-td>
        </template>
        <template v-slot:body-cell-source="props">
          <q-td :props="props">
            <div class="text-weight-medium ellipsis" :title="props.row.mailbox_account">
              {{ sourceTypeLabel(props.row.source_type) }} · {{ props.row.mailbox_account || '-' }}
            </div>
            <div v-if="props.row.sender_name" class="text-caption text-grey-7 ellipsis" :title="props.row.sender_name">
              {{ props.row.sender_name }}
            </div>
            <div class="text-caption text-grey-7 ellipsis" :title="props.row.sender_email || props.row.sender_name">
              From: {{ compactEmail(props.row.sender_email) || props.row.sender_name || '-' }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-status="props">
          <q-td :props="props">
            <q-badge :color="statusColor(props.row.status)">{{ statusLabel(props.row.status) }}</q-badge>
            <div v-if="props.row.exception_summary" class="source-intake-exception-marker" :title="props.row.exception_summary">
              <q-icon name="warning" size="14px" /> Exception
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-reference="props">
          <q-td :props="props">
            <div class="text-weight-medium ellipsis" :title="props.row.external_reference || props.row.matched_entity_ref">
              {{ props.row.external_reference || props.row.matched_entity_ref || '-' }}
            </div>
            <div class="text-caption text-grey-7 ellipsis" :title="props.row.subject">
              {{ props.row.subject || 'No subject' }}
            </div>
            <div class="text-caption text-grey-7">Evidence #{{ props.row.source_evidence_id || '-' }}</div>
            <div v-if="props.row.matched_entity_ref" class="text-caption text-grey-7 ellipsis">
              {{ props.row.matched_entity_type || 'Matched' }}: {{ props.row.matched_entity_ref }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-next_action="props">
          <q-td
            :props="props"
            class="source-intake-next ellipsis"
            :title="props.row.next_action || props.row.exception_summary || ''"
          >{{ props.row.next_action || (props.row.exception_summary ? 'Review exception' : '-') }}</q-td>
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
          <div>
            <div class="text-h6">Source Record {{ detail ? detail.id : '' }}</div>
            <div v-if="detail" class="text-caption text-grey-7">Evidence {{ detail.source_evidence_id }}</div>
          </div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup aria-label="Close" />
        </q-card-section>
        <q-separator />
        <q-card-section v-if="detail">
          <div class="source-intake-section-title">Source</div>
          <div class="source-intake-detail-grid">
            <div><span>Status</span><strong><q-badge :color="statusColor(detail.status)">{{ statusLabel(detail.status) }}</q-badge></strong></div>
            <div><span>Operation</span><strong>{{ operationLabel(detail.operation) }}</strong></div>
            <div><span>Document</span><strong>{{ documentLabel(detail.document_type) }}</strong></div>
            <div><span>Reference</span><strong>{{ detail.external_reference || '-' }}</strong></div>
          </div>
          <q-separator class="q-my-md" />
          <div class="source-intake-section-title">Original Email</div>
          <div class="source-intake-source-card q-pa-sm q-mb-md">
            <div class="source-intake-detail-grid">
              <div><span>Channel</span><strong>{{ sourceTypeLabel(detail.source_type) }}</strong></div>
              <div><span>Mailbox</span><strong>{{ detail.mailbox_account || '-' }}</strong></div>
              <div><span>From</span><strong>{{ originalEmail(detail).sender_name || detail.sender_name || '-' }}</strong></div>
              <div><span>Sender email</span><strong>{{ originalEmail(detail).sender_email || detail.sender_email || '-' }}</strong></div>
              <div><span>Sent by customer</span><strong>{{ originalEmail(detail).sent_at_raw || formatSourceTime(originalEmail(detail).sent_at || detail.sent_at) }}</strong></div>
              <div><span>Received by mailbox</span><strong>{{ formatDate(forwardedEmail(detail).received_at || detail.received_at) }}</strong></div>
              <div><span>Evidence ID</span><strong>#{{ detail.source_evidence_id || '-' }}</strong></div>
              <div><span>Captured</span><strong>{{ formatDate(detail.captured_at) }}</strong></div>
            </div>
            <div v-if="originalEmail(detail).from_raw" class="source-intake-field-label q-mt-md">Original From header</div>
            <div v-if="originalEmail(detail).from_raw" class="source-intake-wrap">{{ originalEmail(detail).from_raw }}</div>
            <div v-if="originalEmail(detail).to && originalEmail(detail).to.length" class="source-intake-field-label q-mt-md">To</div>
            <div v-if="originalEmail(detail).to && originalEmail(detail).to.length" class="source-intake-wrap">{{ formatRecipients(originalEmail(detail).to) }}</div>
            <div v-if="originalEmail(detail).cc && originalEmail(detail).cc.length" class="source-intake-field-label q-mt-md">Cc</div>
            <div v-if="originalEmail(detail).cc && originalEmail(detail).cc.length" class="source-intake-wrap">{{ formatRecipients(originalEmail(detail).cc) }}</div>
            <div class="source-intake-field-label q-mt-md">Subject</div>
            <div class="source-intake-wrap">{{ originalEmail(detail).subject || detail.subject || '-' }}</div>
            <div class="source-intake-field-label q-mt-md">Message ID / Thread ID</div>
            <div class="source-intake-wrap source-intake-mono">{{ originalEmail(detail).message_id || '-' }} / {{ originalEmail(detail).thread_id || detail.thread_id || '-' }}</div>
            <div class="source-intake-field-label q-mt-md">Original email content</div>
            <div v-if="detail.email_body" class="source-intake-wrap">{{ detail.email_body }}</div>
            <div v-else class="text-caption text-grey-7">Original email body was not captured. Review the subject, extracted fields and attachments below.</div>
            <div v-if="hasForwardedEmail(detail)" class="source-intake-forwarded q-pa-sm q-mt-md">
              <div class="text-weight-medium q-mb-xs">Forwarding context</div>
              <div class="source-intake-detail-grid">
                <div><span>Forwarded by</span><strong>{{ forwardedEmail(detail).sender_name || forwardedEmail(detail).sender_email || '-' }}</strong></div>
                <div><span>Forwarder email</span><strong>{{ forwardedEmail(detail).sender_email || '-' }}</strong></div>
                <div><span>Forwarded subject</span><strong>{{ forwardedEmail(detail).subject || '-' }}</strong></div>
                <div><span>Forwarded received</span><strong>{{ formatDate(forwardedEmail(detail).received_at) }}</strong></div>
              </div>
              <div class="text-caption text-grey-7 q-mt-sm">The forwarded message is retained as evidence, but is not the customer source used for business extraction.</div>
            </div>
          </div>
          <div class="source-intake-section-title">Business Link</div>
          <div class="source-intake-detail-grid">
            <div><span>Matched entity</span><strong>{{ detail.matched_entity_type || '-' }}</strong></div>
            <div><span>Entity reference</span><strong>{{ detail.matched_entity_ref || '-' }}</strong></div>
            <div><span>Owner role</span><strong>{{ detail.owner_role || '-' }}</strong></div>
            <div><span>Classification</span><strong>{{ confidenceLabel(detail.classification_confidence) }}</strong></div>
          </div>
          <div class="source-intake-field-label q-mt-md">Next step</div>
          <div class="q-mb-md source-intake-wrap">{{ detail.next_action || '-' }}</div>
          <div v-if="detail.exception_summary" class="source-intake-exception q-pa-sm q-mb-md">
            <div class="text-weight-medium q-mb-xs"><q-icon name="warning" /> Exception</div>
            <div>{{ detail.exception_summary }}</div>
          </div>
          <div class="source-intake-section-title">Information From Email</div>
          <div v-if="extractionRows.length" class="source-intake-extractions">
            <div v-for="item in extractionRows" :key="item.key" class="source-intake-extraction q-pa-sm q-mb-xs">
              <div class="row items-center q-col-gutter-sm">
                <div class="col text-weight-medium">{{ item.label }}</div>
                <div v-if="item.confidence" class="col-auto text-caption text-grey-7">{{ item.confidence }}</div>
              </div>
              <div class="source-intake-wrap">{{ item.value }}</div>
              <div v-if="item.source_location" class="text-caption text-grey-7">Source: {{ item.source_location }}</div>
              <div v-if="item.flags" class="text-caption text-grey-7">{{ item.flags }}</div>
            </div>
          </div>
          <div v-else class="text-caption text-grey-7 q-mb-md">No extracted fields recorded.</div>
          <div class="source-intake-section-title">Attachments</div>
          <div v-if="detail.attachments && detail.attachments.length">
            <div v-for="attachment in detail.attachments" :key="attachment.id" class="source-intake-attachment q-pa-sm q-mb-xs">
              <div class="text-weight-medium source-intake-wrap">{{ attachment.attachment_name }}</div>
              <div class="text-caption text-grey-7">{{ attachment.content_type || 'file' }} · {{ attachment.security_status }} · {{ formatBytes(attachment.storage_size) }}</div>
              <div v-if="attachment.source_location" class="text-caption text-grey-7">{{ attachment.source_location }}</div>
            </div>
          </div>
          <div v-else class="text-caption text-grey-7">No attachment metadata</div>
          <div class="source-intake-section-title q-mt-md">Evidence</div>
          <div class="source-intake-detail-grid">
            <div><span>Storage</span><strong>{{ detail.storage_uri ? 'Stored · ' + formatBytes(detail.storage_size) : 'Not stored' }}</strong></div>
            <div><span>Content hash</span><strong class="source-intake-hash" :title="detail.content_hash">{{ shortHash(detail.content_hash) }}</strong></div>
          </div>
          <div class="source-intake-section-title q-mt-md">Processing Events</div>
          <q-timeline color="primary" layout="dense">
            <q-timeline-entry v-for="event in (detail.events || [])" :key="event.id" :title="eventLabel(event.event_type)" :subtitle="formatDate(event.created_at)">
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
      total: 0,
      hasMore: false,
      pagination: { rowsPerPage: 0 },
      offset: 0,
      statusOptions: [
        { label: 'Captured', value: 'CAPTURED' },
        { label: 'Analyzing', value: 'ANALYZING' },
        { label: 'Review required', value: 'REVIEW_REQUIRED' },
        { label: 'Ready for preview', value: 'READY_FOR_PREVIEW' },
        { label: 'Approval required', value: 'APPROVAL_REQUIRED' },
        { label: 'Executing', value: 'EXECUTING' },
        { label: 'Completed', value: 'COMPLETED' },
        { label: 'Blocked', value: 'BLOCKED' },
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
        { name: 'received_at', label: 'Sent', field: 'sent_at', align: 'left', style: 'width: 11%' },
        { name: 'document', label: 'Document', field: 'document_type', align: 'left', style: 'width: 13%' },
        { name: 'source', label: 'Original source', field: 'sender_email', align: 'left', style: 'width: 22%' },
        { name: 'reference', label: 'Reference', field: 'external_reference', align: 'left', style: 'width: 15%' },
        { name: 'operation', label: 'Operation', field: 'operation', align: 'left', style: 'width: 9%' },
        { name: 'status', label: 'Status', field: 'status', align: 'left', style: 'width: 13%' },
        { name: 'next_action', label: 'Next step', field: 'next_action', align: 'left', style: 'width: 16%' },
        { name: 'action', label: '', field: 'action', align: 'right', style: 'width: 48px' }
      ]
    }
  },
  computed: {
    countItems () {
      const statuses = [
        { key: 'CAPTURED', label: 'Captured' },
        { key: 'ANALYZING', label: 'Analyzing' },
        { key: 'REVIEW_REQUIRED', label: 'Review' },
        { key: 'READY_FOR_PREVIEW', label: 'Ready' },
        { key: 'APPROVAL_REQUIRED', label: 'Approval' },
        { key: 'EXECUTING', label: 'Executing' },
        { key: 'COMPLETED', label: 'Completed' },
        { key: 'BLOCKED', label: 'Blocked' },
        { key: 'DUPLICATE', label: 'Duplicate' },
        { key: 'FAILED', label: 'Failed' }
      ]
      return [{ key: '__TOTAL__', label: 'Total', color: 'grey-8', value: this.total }].concat(
        statuses
          .filter(item => Number(this.counts[item.key] || 0) > 0)
          .map(item => ({ ...item, color: this.statusColor(item.key), value: this.counts[item.key] }))
      )
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
          this.total = Number(res.total || 0)
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
          this.total = Number(res.total || this.total)
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
    formatSourceTime (value) {
      return value ? this.formatDate(value) : 'Not provided'
    },
    compactEmail (value) {
      const email = String(value || '')
      if (email.length <= 30) return email
      const at = email.lastIndexOf('@')
      if (at <= 0) return `${email.slice(0, 12)}…${email.slice(-10)}`
      const domain = email.slice(at + 1)
      const local = email.slice(0, at)
      const localBudget = Math.max(8, 27 - domain.length)
      return `${local.slice(0, localBudget)}…@${domain}`
    },
    originalEmail (detail) {
      return (detail && detail.original_email) || {}
    },
    forwardedEmail (detail) {
      return (detail && detail.forwarded_email) || {}
    },
    hasForwardedEmail (detail) {
      const email = this.forwardedEmail(detail)
      return Boolean(email.sender_name || email.sender_email || email.subject || email.received_at)
    },
    formatRecipients (value) {
      return Array.isArray(value) ? value.join('; ') : String(value || '-')
    },
    statusLabel (value) {
      return {
        CAPTURED: 'Captured',
        ANALYZING: 'Analyzing',
        REVIEW_REQUIRED: 'Review required',
        READY_FOR_PREVIEW: 'Ready',
        APPROVAL_REQUIRED: 'Approval required',
        EXECUTING: 'Executing',
        COMPLETED: 'Completed',
        BLOCKED: 'Blocked',
        DUPLICATE: 'Duplicate',
        FAILED: 'Failed'
      }[value] || value || 'Unknown'
    },
    operationLabel (value) {
      return { INBOUND: 'Inbound', OUTBOUND: 'Outbound', SUPPORTING: 'Supporting', UNKNOWN: 'Unknown' }[value] || value || '-'
    },
    documentLabel (value) {
      return {
        INBOUND_NOTICE: 'Inbound notice',
        PACK_LIST: 'Pack list',
        PICK_TICKET: 'Pick ticket',
        DELIVERY_REQUEST: 'Delivery request',
        APPOINTMENT: 'Appointment',
        QC_SCAN: 'QC / scan sheet',
        OTHER: 'Other'
      }[value] || value || 'Other'
    },
    sourceTypeLabel (value) {
      return { EMAIL: 'Email', AI_AGENT: 'AI agent', WEB_FORM: 'Web form', CLI: 'CLI' }[value] || value || 'Source'
    },
    confidenceLabel (value) {
      if (value === null || value === undefined || value === '') return 'Not recorded'
      const numeric = Number(value)
      return Number.isNaN(numeric) ? String(value) : `${Math.round(numeric * 100)}%`
    },
    extractionRows () {
      if (!this.detail) return []
      const items = (this.detail.extractions || []).map((item, index) => ({
        key: `extraction-${index}-${item.field_name}`,
        label: this.fieldLabel(item.field_name),
        value: item.normalized_value || item.raw_value || '-',
        source_location: item.source_location,
        confidence: item.confidence === null || item.confidence === undefined ? '' : `${Math.round(Number(item.confidence) * 100)}% confidence`,
        flags: [item.human_confirmed ? 'Human confirmed' : '', item.used_for_write ? 'Used for write' : ''].filter(Boolean).join(' · ')
      }))
      if (items.length) return items
      const metadata = this.detail.metadata || {}
      const keys = ['container_no', 'eta', 'requested_delivery_date', 'customer', 'customer_address', 'receiving_address', 'warehouse', 'appointment_status', 'external_reference', 'business_operation']
      return keys.filter(key => metadata[key] !== undefined && metadata[key] !== null && metadata[key] !== '').map(key => ({
        key: `metadata-${key}`,
        label: this.fieldLabel(key),
        value: this.formatValue(metadata[key]),
        source_location: 'Email metadata',
        confidence: '',
        flags: ''
      }))
    },
    fieldLabel (value) {
      return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()) || 'Field'
    },
    formatValue (value) {
      return typeof value === 'object' ? JSON.stringify(value) : String(value)
    },
    formatBytes (value) {
      const bytes = Number(value || 0)
      if (!bytes) return 'Size unavailable'
      if (bytes < 1024) return `${bytes} B`
      if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
      return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    },
    shortHash (value) {
      if (!value) return '-'
      const hash = String(value)
      return hash.length > 18 ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : hash
    },
    eventLabel (value) {
      return this.fieldLabel(value)
    },
    statusColor (value) {
      return {
        CAPTURED: 'grey-7',
        ANALYZING: 'blue-grey-7',
        REVIEW_REQUIRED: 'orange-8',
        READY_FOR_PREVIEW: 'teal-7',
        APPROVAL_REQUIRED: 'blue-8',
        EXECUTING: 'indigo-7',
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
  background: #f5f5f5;
}

.source-intake-card {
  width: 100%;
  box-shadow: 0 2px 12px rgba(25, 49, 74, 0.08);
}

.source-intake-table {
  margin-top: 12px;
  table-layout: fixed;
  width: 100%;
}

.source-intake-next {
  max-width: 0;
  white-space: nowrap;
}

.source-intake-exception-marker {
  color: #c76a00;
  font-size: 11px;
  margin-top: 3px;
  white-space: nowrap;
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

.source-intake-source-card {
  background: #f8fafb;
  border: 1px solid #dfe7eb;
  border-left: 3px solid #1976d2;
}

.source-intake-forwarded {
  background: #fffaf0;
  border: 1px solid #ead8b3;
  border-left: 3px solid #d28b16;
}

.source-intake-section-title {
  color: #263238;
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
}

.source-intake-field-label {
  color: #78909c;
  font-size: 11px;
  margin-bottom: 4px;
  text-transform: uppercase;
}

.source-intake-wrap {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.source-intake-exception {
  background: #fff3e0;
  color: #8d4a00;
}

.source-intake-attachment {
  background: #f5f7f9;
  border: 1px solid #e0e6ea;
}

.source-intake-extraction {
  background: #f8fafb;
  border: 1px solid #e0e6ea;
}

.source-intake-hash {
  font-family: monospace;
}

.source-intake-mono {
  font-family: monospace;
}
</style>
