<template>
  <div class="mail-task-board-shell q-mt-sm">
    <q-card class="mail-task-board shadow-11">
      <q-card-section class="mail-task-board__header row items-center q-px-md q-py-sm">
        <div class="mail-task-board__title">MAIL TO TASK</div>
        <q-space />
        <div v-if="previewMode" class="mail-task-board__preview">PREVIEW</div>
        <div class="mail-task-board__live">LIVE</div>
        <q-btn flat round dense color="white" icon="refresh" :loading="loading" aria-label="Refresh mail tasks" @click="getList" />
      </q-card-section>

      <q-card-section class="mail-task-board__summary row items-center q-px-md q-py-xs">
        <div class="mail-task-board__subtitle">Incoming email work queue</div>
        <q-space />
        <div class="mail-task-board__counts">
          <span class="mail-task-board__count">OPEN {{ summary.open }}</span>
          <span class="mail-task-board__count mail-task-board__count--due">DUE {{ summary.due }}</span>
          <span class="mail-task-board__count mail-task-board__count--review">REVIEW {{ summary.review }}</span>
        </div>
      </q-card-section>

      <q-card-section class="mail-task-board__controls row items-center q-pa-none">
        <q-tabs v-model="activeFilter" dense align="left" active-color="primary" indicator-color="primary" class="mail-task-board__filters">
          <q-tab name="all" label="All" />
          <q-tab name="inbound" label="IB" />
          <q-tab name="outbound" label="OB" />
          <q-tab name="review" label="Review" />
        </q-tabs>
        <q-space />
        <q-badge outline color="primary" class="mail-task-board__source q-mr-sm">PS MAIL</q-badge>
      </q-card-section>

      <q-banner v-if="feedMessage" dense class="mail-task-board__notice">
        <q-icon name="info" size="16px" class="q-mr-sm" />
        {{ feedMessage }}
        <template v-slot:action>
          <q-btn v-if="apiEnabled" flat dense color="primary" label="Retry" @click="getList" />
        </template>
      </q-banner>

      <q-table
        class="mail-task-board__table"
        table-class="mail-task-board__grid"
        :data="filteredItems"
        :columns="columns"
        row-key="id"
        dense
        flat
        bordered
        separator="horizontal"
        hide-bottom
        :pagination.sync="pagination"
        :loading="loading"
        :row-class="rowClass"
        :no-data-label="noDataLabel"
      >
        <template v-slot:body-cell-task="props">
          <q-td :props="props">
            <button type="button" class="mail-task-board__task" @click="showDetails(props.row)">
              <span class="mail-task-board__task-line">
                <q-badge outline :color="typeColor(props.row)">{{ typeLabel(props.row) }}</q-badge>
                <span class="mail-task-board__task-key" :title="props.row.task_key || props.row.id">{{ compactReference(props.row.task_key || props.row.id) }}</span>
              </span>
              <span class="mail-task-board__subject" :title="props.row.subject">{{ shortSubject(props.row.subject) }}</span>
            </button>
          </q-td>
        </template>

        <template v-slot:body-cell-owner="props">
          <q-td :props="props">
            <span class="mail-task-board__owner" :title="props.row.assignee_name || props.row.assigned_to">{{ ownerLabel(props.row) }}</span>
          </q-td>
        </template>

        <template v-slot:body-cell-next="props">
          <q-td :props="props" class="mail-task-board__next-cell">
            <span class="mail-task-board__next" :title="nextAction(props.row)">{{ compactText(nextAction(props.row), 24) }}</span>
          </q-td>
        </template>

        <template v-slot:body-cell-wms="props">
          <q-td :props="props">
            <span class="mail-task-board__wms" :title="wmsReference(props.row)">{{ compactReference(wmsReference(props.row)) }}</span>
          </q-td>
        </template>

        <template v-slot:body-cell-status="props">
          <q-td :props="props" class="mail-task-board__status-cell">
            <q-badge class="mail-task-board__status" :color="statusColor(props.row)">{{ statusLabel(props.row) }}</q-badge>
          </q-td>
        </template>

        <template v-slot:body-cell-action="props">
          <q-td :props="props">
            <q-btn flat dense color="primary" icon="open_in_new" aria-label="Open task" @click="showDetails(props.row)" />
          </q-td>
        </template>
      </q-table>
    </q-card>

    <q-dialog v-model="detailOpen" position="right">
      <q-card v-if="selectedTask" class="mail-task-board__detail">
        <q-card-section class="row items-center q-pb-sm">
          <div>
            <div class="text-subtitle1 text-weight-bold">{{ compactReference(selectedTask.task_key || selectedTask.id) }}</div>
            <div class="text-caption text-grey-7">{{ typeLabel(selectedTask) }} · {{ statusLabel(selectedTask) }}</div>
          </div>
          <q-space />
          <q-btn flat round dense icon="close" @click="detailOpen = false" />
        </q-card-section>
        <q-separator />
        <q-card-section class="mail-task-board__detail-body">
          <div class="mail-task-board__detail-status row items-center q-mb-md">
            <q-badge :color="statusColor(selectedTask)">{{ statusLabel(selectedTask) }}</q-badge>
            <q-space />
            <span class="text-caption text-grey-7">{{ ownerLabel(selectedTask) }}</span>
          </div>

          <div class="mail-task-board__detail-grid">
            <div class="mail-task-board__detail-label">Subject</div>
            <div class="mail-task-board__detail-value">{{ selectedTask.subject || '—' }}</div>
            <div class="mail-task-board__detail-label">Sender</div>
            <div class="mail-task-board__detail-value">{{ selectedTask.sender || selectedTask.from || '—' }}</div>
            <div class="mail-task-board__detail-label">Received</div>
            <div class="mail-task-board__detail-value">{{ formatDate(selectedTask.received_at || selectedTask.received_time) }}</div>
            <div class="mail-task-board__detail-label">Next</div>
            <div class="mail-task-board__detail-value">{{ nextAction(selectedTask) }}</div>
            <div class="mail-task-board__detail-label">WMS Ref</div>
            <div class="mail-task-board__detail-value">{{ wmsReference(selectedTask) }}</div>
            <div class="mail-task-board__detail-label">Files</div>
            <div class="mail-task-board__detail-value">{{ attachmentLabel(selectedTask) }}</div>
          </div>

          <div v-if="selectedTask.source_message_key" class="mail-task-board__detail-section">
            <div class="mail-task-board__detail-label">Source Message</div>
            <div class="mail-task-board__message-key" :title="selectedTask.source_message_key">{{ selectedTask.source_message_key }}</div>
          </div>

          <div v-if="selectedTask.note || selectedTask.exception_summary" class="mail-task-board__detail-section">
            <div class="mail-task-board__detail-label">Note</div>
            <div class="mail-task-board__detail-note">{{ selectedTask.note || selectedTask.exception_summary }}</div>
          </div>

          <q-banner v-if="previewMode" dense rounded class="bg-blue-1 text-primary q-mt-md">
            Preview rows are local-only. Live tasks will be supplied by the controlled MailTask API.
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request.js'

export default {
  name: 'MailTaskBoard',
  data () {
    return {
      activeFilter: 'all',
      items: [],
      counts: {},
      loading: false,
      apiEnabled: false,
      previewMode: false,
      feedMessage: '',
      refreshTimer: null,
      pagination: { rowsPerPage: 0 },
      detailOpen: false,
      selectedTask: null
    }
  },
  computed: {
    columns () {
      return [
        { name: 'task', label: 'Task', field: 'task_key', align: 'left', style: 'min-width: 250px; width: 32%;', headerStyle: 'min-width: 250px; width: 32%;' },
        { name: 'owner', label: 'Owner', field: 'assigned_to', align: 'left', style: 'min-width: 90px; width: 12%;', headerStyle: 'min-width: 90px; width: 12%;' },
        { name: 'next', label: 'Next', field: 'next_action', align: 'left', style: 'min-width: 150px; width: 20%;', headerStyle: 'min-width: 150px; width: 20%;' },
        { name: 'wms', label: 'WMS', field: 'wms_reference', align: 'left', style: 'min-width: 120px; width: 16%;', headerStyle: 'min-width: 120px; width: 16%;' },
        { name: 'status', label: 'Status', field: 'status', align: 'left', style: 'min-width: 110px; width: 14%;', headerStyle: 'min-width: 110px; width: 14%;' },
        { name: 'action', label: '', field: 'action', align: 'right' }
      ]
    },
    filteredItems () {
      if (this.activeFilter === 'all') return this.items
      return this.items.filter(item => this.matchesFilter(item, this.activeFilter))
    },
    summary () {
      const rows = this.items
      const open = this.numberOrCount('open', rows.filter(row => !this.isClosed(row)).length)
      const due = this.numberOrCount('due', rows.filter(row => ['DUE', 'URGENT', 'OVERDUE'].includes(String(row.priority || row.eta_status || '').toUpperCase())).length)
      const review = this.numberOrCount('review', rows.filter(row => this.matchesFilter(row, 'review')).length)
      return {
        open,
        due,
        review
      }
    },
    noDataLabel () {
      if (this.previewMode) return 'No preview tasks'
      if (this.apiEnabled) return 'No mail tasks'
      return 'MailTask feed is not enabled'
    }
  },
  mounted () {
    this.previewMode = this.isPreviewRequest()
    this.apiEnabled = Boolean(window.__GREATERWMS_MAILTASK_API__)
    if (this.previewMode) {
      this.items = this.previewRows()
      this.feedMessage = 'Preview only · live mailbox data is not used.'
      return
    }
    if (this.apiEnabled) {
      this.getList()
      this.refreshTimer = setInterval(() => this.getList(), 30000)
    } else {
      this.feedMessage = 'Task feed staged · enable the controlled MailTask API to show live email tasks.'
    }
  },
  beforeDestroy () {
    if (this.refreshTimer) clearInterval(this.refreshTimer)
  },
  methods: {
    getList () {
      if (!this.apiEnabled || !this.$q.localStorage.has('auth')) return
      this.loading = true
      this.feedMessage = ''
      const endpoint = window.__GREATERWMS_MAILTASK_API__
      getauth(`${endpoint}?limit=200&offset=0`)
        .then(res => {
          this.items = res.items || []
          this.counts = res.counts || {}
        })
        .catch(() => {
          this.feedMessage = 'MailTask feed unavailable · no email rows were changed.'
        })
        .finally(() => {
          this.loading = false
        })
    },
    isPreviewRequest () {
      const query = new URLSearchParams(window.location.search || '')
      return ['localhost', '127.0.0.1', '::1'].includes(window.location.hostname) && query.get('mailtask_preview') === '1'
    },
    previewRows () {
      return [
        {
          id: 'preview-ib-001',
          task_key: 'MT-IB-001',
          task_type: 'IB',
          subject: 'Delta receiving notice · ASN 240824-01',
          sender: 'Delta Logistics',
          received_at: '2026-08-24T11:38:00',
          assigned_to: 'Maggie',
          next_action: 'Create inbound order',
          wms_reference: 'ASN-240824-01',
          status: 'READY_FOR_WMS',
          attachment_count: 2,
          source_message_key: 'preview/message/001'
        },
        {
          id: 'preview-ob-001',
          task_key: 'MT-OB-001',
          task_type: 'OB',
          subject: 'Outbound BOL revision · confirm ship date',
          sender: 'Peak Logistics',
          received_at: '2026-08-24T11:44:00',
          assigned_to: 'Sunny',
          next_action: 'Approve outbound change',
          wms_reference: 'DO-240824-07',
          status: 'SUNNY_APPROVAL',
          priority: 'DUE',
          attachment_count: 1,
          source_message_key: 'preview/message/002'
        },
        {
          id: 'preview-review-001',
          task_key: 'MT-REVIEW-001',
          task_type: 'REVIEW',
          subject: 'BOL and DO details do not match',
          sender: 'Delta Forwarder',
          received_at: '2026-08-24T11:42:00',
          assigned_to: 'Sunny',
          next_action: 'Review exception',
          wms_reference: '—',
          status: 'NEEDS_REVIEW',
          attachment_count: 1,
          source_message_key: 'preview/message/003',
          exception_summary: 'Reference change requires confirmation before WMS update.'
        }
      ]
    },
    matchesFilter (row, filter) {
      const type = String(row.task_type || row.category || row.operation || '').toUpperCase()
      const status = String(row.status || row.business_status || '').toUpperCase()
      if (filter === 'inbound') return type === 'IB' || type.includes('INBOUND')
      if (filter === 'outbound') return type === 'OB' || type.includes('OUTBOUND')
      if (filter === 'review') return type === 'REVIEW' || status.includes('REVIEW') || status.includes('EXCEPTION') || status === 'BLOCKED'
      return true
    },
    numberOrCount (key, fallback) {
      const value = Number(this.counts[key])
      return Number.isFinite(value) ? value : fallback
    },
    isClosed (row) {
      return ['COMPLETED', 'CLOSED', 'CANCELLED'].includes(String(row.status || row.business_status || '').toUpperCase())
    },
    compactReference (value) {
      const code = String(value || '').trim()
      if (!code || code === '—') return '—'
      if (code.length <= 16) return code
      return `${code.slice(0, 7)}…${code.slice(-6)}`
    },
    compactText (value, length) {
      const text = String(value || '').trim()
      if (text.length <= length) return text || '—'
      return `${text.slice(0, length - 1)}…`
    },
    shortSubject (value) {
      return this.compactText(value, 52)
    },
    typeLabel (row) {
      const type = String((row && (row.task_type || row.category || row.operation)) || '').toUpperCase()
      if (type.includes('INBOUND') || type === 'RECEIVING' || type === 'IB') return 'IB'
      if (type.includes('OUTBOUND') || type === 'OB') return 'OB'
      if (type.includes('REVIEW') || type.includes('EXCEPTION')) return 'REV'
      if (type.includes('MOVE') || type.includes('TRANSFER')) return 'MOVE'
      return type ? this.compactText(type, 5) : 'TASK'
    },
    typeColor (row) {
      return { IB: 'primary', OB: 'deep-orange', REV: 'negative', MOVE: 'purple' }[this.typeLabel(row)] || 'grey-7'
    },
    ownerLabel (row) {
      const value = String((row && (row.assignee_name || row.assigned_to || row.owner)) || '').trim()
      if (!value) return 'Unassigned'
      return this.compactText(value, 14)
    },
    nextAction (row) {
      return (row && (row.next_action_label || row.next_action || row.action)) || 'Review task'
    },
    wmsReference (row) {
      return (row && (row.wms_reference || row.wms_ref || row.external_reference)) || '—'
    },
    statusLabel (row) {
      const value = String((row && (row.status || row.business_status)) || '').toUpperCase()
      const labels = {
        READY_FOR_WMS: 'READY',
        MAGGIE_INPUT: 'MAGGIE',
        SUNNY_APPROVAL: 'APPROVAL',
        NEEDS_REVIEW: 'REVIEW',
        IN_PROGRESS: 'WORKING',
        COMPLETED: 'DONE',
        CANCELLED: 'CANCELLED'
      }
      return labels[value] || this.compactText(value.replace(/_/g, ' '), 12) || 'OPEN'
    },
    statusColor (row) {
      const value = String((row && (row.status || row.business_status)) || '').toUpperCase()
      if (['COMPLETED', 'CLOSED', 'READY_FOR_WMS'].includes(value)) return 'positive'
      if (['NEEDS_REVIEW', 'BLOCKED', 'EXCEPTION'].includes(value) || value.includes('REVIEW')) return 'negative'
      if (value.includes('APPROVAL') || value === 'DUE') return 'warning'
      if (value.includes('MAGGIE') || value === 'IN_PROGRESS') return 'primary'
      if (value === 'CANCELLED') return 'grey-7'
      return 'grey-7'
    },
    formatDate (value) {
      const normalized = String(value || '').replace('T', ' ')
      const match = normalized.match(/^(?:\d{4}-)?(\d{2})[-/](\d{2})\s+(\d{2}:\d{2})/)
      return match ? `${match[1]}/${match[2]} ${match[3]}` : this.compactText(normalized, 20) || '—'
    },
    attachmentLabel (row) {
      const count = Number(row && (row.attachment_count || row.attachments_count))
      if (Number.isFinite(count)) return `${count} file${count === 1 ? '' : 's'}`
      if (Array.isArray(row && row.attachments)) return `${row.attachments.length} files`
      return '—'
    },
    rowClass (row) {
      return `mail-task-board__row--${this.typeLabel(row).toLowerCase()}`
    },
    showDetails (row) {
      this.selectedTask = row
      this.detailOpen = true
    }
  }
}
</script>

<style scoped>
.mail-task-board-shell { width: 100%; }
.mail-task-board { width: 100%; background: #ffffff; border-radius: 2px; }
.mail-task-board__header { min-height: 48px; background: #596782; color: #ffffff; }
.mail-task-board__title { font-size: 16px; font-weight: 700; letter-spacing: 0.08em; }
.mail-task-board__live { margin-right: 8px; color: #8ee3a7; font-size: 11px; font-weight: 700; letter-spacing: 0.12em; }
.mail-task-board__preview { margin-right: 14px; color: #ffd166; font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.mail-task-board__summary { min-height: 40px; border-bottom: 1px solid #dfe3ea; }
.mail-task-board__subtitle { color: #667085; font-size: 12px; font-weight: 600; }
.mail-task-board__counts { display: flex; gap: 12px; color: #667085; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; }
.mail-task-board__count--due { color: #b54708; }
.mail-task-board__count--review { color: #b42318; }
.mail-task-board__controls { min-height: 38px; background: #f5f6f8; border-bottom: 1px solid #dfe3ea; }
.mail-task-board__filters { min-height: 38px; }
.mail-task-board__source { font-size: 10px; letter-spacing: 0.06em; }
.mail-task-board__notice { border-bottom: 1px solid #dfe3ea; background: #fff8e6; color: #7a5b00; font-size: 12px; }
.mail-task-board__table >>> .q-table thead tr th { height: 38px; background: #3f4b69; color: #ffffff; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
.mail-task-board__table >>> .q-table__middle { width: 100%; overflow-x: auto; }
.mail-task-board__table >>> .q-table { min-width: 880px; }
.mail-task-board__table >>> .q-table th, .mail-task-board__table >>> .q-table td { white-space: nowrap; }
.mail-task-board__table >>> .q-table tbody tr { min-height: 52px; }
.mail-task-board__table >>> .q-table tbody tr:nth-child(even) { background: #f7f8fb; }
.mail-task-board__table >>> .q-table tbody tr:hover { background: #eaf0f8; }
.mail-task-board__task { display: block; max-width: 100%; padding: 0; border: 0; background: transparent; color: #334155; cursor: pointer; font: inherit; text-align: left; }
.mail-task-board__task:hover { color: #1976d2; }
.mail-task-board__task-line { display: flex; align-items: center; gap: 7px; }
.mail-task-board__task-key { font-weight: 700; }
.mail-task-board__subject { display: block; max-width: 360px; margin-top: 3px; overflow: hidden; color: #667085; font-size: 11px; text-overflow: ellipsis; }
.mail-task-board__owner { font-weight: 600; }
.mail-task-board__next-cell, .mail-task-board__status-cell { white-space: normal !important; vertical-align: middle; }
.mail-task-board__next { display: block; max-width: 210px; white-space: normal; overflow-wrap: anywhere; line-height: 1.25; font-weight: 600; }
.mail-task-board__wms { color: #475467; font-family: monospace; font-size: 12px; }
.mail-task-board__status { max-width: 100%; white-space: normal; line-height: 1.25; text-align: center; }
.mail-task-board__detail { width: min(440px, 92vw); max-width: 440px; min-height: 100vh; }
.mail-task-board__detail-body { overflow-y: auto; }
.mail-task-board__detail-status { border-bottom: 1px solid #eaecf0; padding-bottom: 12px; }
.mail-task-board__detail-grid { display: grid; grid-template-columns: 100px 1fr; gap: 11px 14px; font-size: 13px; }
.mail-task-board__detail-label { color: #667085; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }
.mail-task-board__detail-value { min-width: 0; overflow-wrap: anywhere; }
.mail-task-board__detail-section { margin-top: 20px; padding-top: 14px; border-top: 1px solid #eaecf0; }
.mail-task-board__message-key { margin-top: 7px; color: #475467; font-family: monospace; font-size: 12px; overflow-wrap: anywhere; }
.mail-task-board__detail-note { margin-top: 7px; color: #475467; line-height: 1.5; }
@media (max-width: 599px) {
  .mail-task-board__table >>> .q-table { min-width: 880px; }
  .mail-task-board__counts { gap: 6px; font-size: 10px; }
  .mail-task-board__subtitle { display: none; }
}
</style>
