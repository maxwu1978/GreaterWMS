<template>
  <q-page class="source-intake-page operations-board-shell q-pa-sm">
    <q-card class="source-intake-card operations-board shadow-11">
      <q-card-section class="operations-board__header row items-center q-px-md q-py-sm">
        <div class="operations-board__title">Mail2Task</div>
        <q-space />
        <div class="operations-board__live">LIVE</div>
        <q-btn flat round dense icon="refresh" :loading="loading" aria-label="Refresh" @click="load" />
      </q-card-section>

      <q-card-section class="operations-board__summary source-intake-summary row items-center q-px-md q-py-xs">
        <div class="operations-board__subtitle">Email-derived tasks · evidence · ownership · WMS handoff</div>
        <q-space />
        <div class="operations-board__counts source-intake-counts">
          <span
            v-for="item in countItems"
            :key="item.key"
            class="operations-board__count"
            :class="{ 'operations-board__count--urgent': item.key === 'AWAITING_SUNNY_APPROVAL', 'operations-board__count--blocked': item.key === 'BLOCKED' }"
          >{{ item.label }} {{ item.value }}</span>
        </div>
      </q-card-section>

      <q-banner v-if="previewMode" dense class="source-intake-preview-banner q-mx-md q-mt-sm">
        <template v-slot:avatar><q-icon name="visibility" color="primary" /></template>
        Local development preview · demonstration data only. No mailbox, WMS or task API writes are performed.
      </q-banner>

      <q-card-section class="operations-board__controls source-intake-filters row items-center q-col-gutter-sm q-px-md q-py-sm">
        <div class="col-12 col-sm-4 col-md-3">
          <q-select v-model="status" dense outlined clearable emit-value map-options :options="statusOptions" label="Status" @input="load" />
        </div>
        <div class="col-12 col-sm-4 col-md-3">
          <q-select v-model="operation" dense outlined clearable emit-value map-options :options="operationOptions" label="Operation" @input="load" />
        </div>
        <div class="col-12 col-sm-4 col-md-2">
          <q-select v-model="taskStatus" dense outlined clearable emit-value map-options :options="taskStatusOptions" label="Task status" @input="load" />
        </div>
        <div class="col-12 col-sm-4 col-md-3">
          <q-input v-model="search" dense outlined clearable label="Search" @keyup.enter="load" />
        </div>
        <div class="col-auto">
          <q-btn color="primary" unelevated label="Search" :loading="loading" @click="load" />
        </div>
      </q-card-section>

      <greater-wms-operations-table
        class="source-intake-table"
        :rows="rows"
        :columns="columns"
        :loading="loading"
        :pagination.sync="pagination"
        :rows-per-page-options="[0]"
        no-data-label="No mail tasks"
      >
        <template v-slot:body-cell-task="props">
          <q-td :props="props">
            <div class="text-weight-medium ellipsis" :title="taskDisplayRef(props.row)">
              {{ taskDisplayRef(props.row) }}
            </div>
            <div class="text-caption text-grey-7 ellipsis" :title="props.row.subject">
              {{ props.row.task_email_count || 1 }} email{{ (props.row.task_email_count || 1) === 1 ? '' : 's' }} · {{ props.row.subject || 'No subject' }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-received_at="props">
          <q-td :props="props">
            <div class="text-weight-medium source-intake-time" :title="'Sent ' + formatDate(props.row.sent_at)">S {{ compactSourceTime(props.row.sent_at) }}</div>
            <div class="text-caption text-grey-7 source-intake-time" :title="'Received in mailbox ' + formatDate(props.row.received_at_raw || props.row.received_at || props.row.captured_at)">R {{ compactSourceTime(props.row.received_at_raw || props.row.received_at || props.row.captured_at) }}</div>
          </q-td>
        </template>
        <template v-slot:body-cell-source="props">
          <q-td :props="props">
            <div class="text-weight-medium ellipsis" :title="props.row.sender_name || 'Unknown sender'">
              {{ props.row.sender_name || 'Unknown sender' }}
            </div>
            <div class="text-caption text-grey-7 ellipsis" :title="props.row.sender_email || props.row.sender_name">
              From: {{ compactEmail(props.row.sender_email) || props.row.sender_name || '-' }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-status="props">
          <q-td :props="props">
            <q-badge :color="taskStatusColor(props.row.task_status || props.row.status)" :title="taskStatusLabel(props.row.task_status || props.row.status)">{{ taskStatusShortLabel(props.row.task_status || props.row.status) }}</q-badge>
            <div class="text-caption text-grey-7" :title="'Email: ' + statusLabel(props.row.status)">Mail: {{ statusShortLabel(props.row.status) }}</div>
            <div v-if="props.row.exception_summary" class="source-intake-exception-marker" :title="props.row.exception_summary">
              <q-icon name="warning" size="14px" /> Exception
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-owner="props">
          <q-td :props="props">
            <div class="text-weight-medium" :title="props.row.assigned_staff_name || props.row.assigned_role_label || ownerLabel(props.row.owner_role)">{{ ownerShortLabel(props.row) }}</div>
            <div class="text-caption text-grey-7 ellipsis" :title="wmsHandoffTooltip(props.row)">
              Handoff: {{ wmsHandoffShortLabel(props.row) }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-reference="props">
          <q-td :props="props">
            <div class="text-weight-medium ellipsis" :title="props.row.external_reference || 'No external reference'">
              {{ compactReference(props.row.external_reference) }}
            </div>
            <div class="text-caption text-grey-7 source-intake-reference-type" :title="referenceTypeTooltip(props.row)">
              {{ operationShortLabel(props.row.operation) }} · {{ documentShortLabel(props.row.document_type) }}
            </div>
          </q-td>
        </template>
        <template v-slot:body-cell-next_action="props">
          <q-td
            :props="props"
            class="source-intake-next"
            :title="nextActionTooltip(props.row)"
          ><span class="source-intake-next-label">{{ nextActionLabel(props.row) }}</span></q-td>
        </template>
        <template v-slot:body-cell-action="props">
          <q-td :props="props"><q-btn flat dense color="primary" icon="open_in_new" aria-label="Open" @click="showDetail(props.row.id)" /></q-td>
        </template>
      </greater-wms-operations-table>

      <q-card-actions align="right" v-if="hasMore" class="q-pa-sm">
        <q-btn flat color="primary" label="Load more" :loading="loading" @click="loadMore" />
      </q-card-actions>
    </q-card>

    <q-dialog v-model="detailOpen" position="right">
      <q-card class="source-intake-detail">
        <q-card-section class="row items-center q-pb-sm">
          <div>
            <div class="text-h6">MailTask {{ detail ? taskDisplayRef(detail) : '' }}</div>
            <div v-if="detail" class="text-caption text-grey-7">Evidence {{ detail.source_evidence_id }} · {{ detail.task_email_count || 1 }} linked email{{ (detail.task_email_count || 1) === 1 ? '' : 's' }}</div>
          </div>
          <q-space />
          <q-btn flat round dense icon="close" v-close-popup aria-label="Close" />
        </q-card-section>
        <q-separator />
        <q-card-section v-if="detail">
          <div class="source-intake-section-title">Task</div>
          <div class="source-intake-detail-grid">
            <div><span>Task status</span><strong><q-badge :color="taskStatusColor(detail.task_status || detail.status)">{{ taskStatusLabel(detail.task_status || detail.status) }}</q-badge></strong></div>
            <div><span>Email status</span><strong>{{ statusLabel(detail.status) }}</strong></div>
            <div><span>Operation</span><strong>{{ operationLabel(detail.operation) }}</strong></div>
            <div><span>Document</span><strong>{{ documentLabel(detail.document_type) }}</strong></div>
            <div><span>Reference</span><strong>{{ detail.external_reference || '-' }}</strong></div>
            <div><span>Owner</span><strong>{{ detail.assigned_staff_name || detail.assigned_role_label || ownerLabel(detail.owner_role) }}</strong></div>
            <div><span>WMS handoff</span><strong>{{ detail.wms_handoff_label || wmsHandoffLabel(detail) }}</strong></div>
            <div><span>WMS reference</span><strong>{{ detail.wms_entity_ref || 'Not recorded' }}</strong></div>
          </div>
          <div class="source-intake-workflow q-mt-md">
            <div class="source-intake-field-label">Role handoff</div>
            <div class="text-weight-medium">{{ nextActionLabel(detail) }}</div>
            <div class="text-caption text-grey-7 source-intake-wrap">{{ rawNextAction(detail) || 'No next action recorded.' }}</div>
            <div class="row q-col-gutter-sm q-mt-sm">
              <div class="col-12 col-sm-5">
                <q-select v-model="assignmentRole" dense outlined emit-value map-options :options="taskRoleOptions" label="Assign role" />
              </div>
              <div class="col-12 col-sm-5">
                <q-select v-model="assignmentStaffId" dense outlined clearable emit-value map-options :options="actorOptions" label="Assign staff" />
              </div>
              <div class="col-12 col-sm-2 flex flex-center">
                <q-btn outline color="primary" label="Assign" :loading="actionLoading" @click="assignTask" />
              </div>
            </div>
            <div v-if="detail.task_actions && detail.task_actions.length" class="row q-gutter-sm q-mt-sm">
              <q-btn
                v-for="action in detail.task_actions"
                :key="action.code"
                dense
                unelevated
                :color="actionButtonColor(action.code)"
                :label="action.label"
                :loading="actionLoading"
                @click="performTaskAction(action.code)"
              />
            </div>
            <div v-else class="text-caption text-grey-7 q-mt-sm">No action is available for the current role and task status.</div>
            <div class="row q-col-gutter-sm q-mt-sm">
              <div class="col-12 col-sm-5">
                <q-select v-model="wmsEntitySystem" dense outlined clearable emit-value map-options :options="wmsSystemOptions" label="WMS system" />
              </div>
              <div class="col-12 col-sm-7">
                <q-input v-model="wmsEntityRef" dense outlined clearable label="WMS reference (required to close)" />
              </div>
            </div>
            <q-input v-model="wmsHandoffNote" class="q-mt-sm" dense outlined type="textarea" autogrow label="Handoff note / site result" />
            <div v-if="detail.approvals && detail.approvals.length" class="source-intake-workflow-history q-mt-md">
              <div class="source-intake-field-label">Sunny approval history</div>
              <div v-for="approval in detail.approvals" :key="approval.id" class="text-caption text-grey-7 q-mt-xs">
                {{ approvalStatusLabel(approval.status) }} · {{ approval.decided_by_name || approval.requested_by_name || 'System' }} · {{ formatDate(approval.decided_at || approval.requested_at) }}
                <span v-if="approval.note"> · {{ approval.note }}</span>
              </div>
            </div>
            <div v-if="detail.task_events && detail.task_events.length" class="source-intake-workflow-history q-mt-md">
              <div class="source-intake-field-label">Task handoff history</div>
              <div v-for="event in detail.task_events" :key="event.id" class="source-intake-workflow-event q-mt-xs">
                <strong>{{ eventLabel(event.action) }}</strong>
                <span class="text-grey-7"> · {{ event.actor_name || event.actor_role || 'System' }} · {{ formatDate(event.created_at) }}</span>
                <div class="text-caption text-grey-7">{{ event.note || event.to_status }}</div>
              </div>
            </div>
          </div>
          <q-separator class="q-my-md" />
          <div class="source-intake-section-title">Original Email</div>
          <div class="source-intake-source-card q-pa-sm q-mb-md">
            <div class="source-intake-detail-grid">
              <div><span>Channel</span><strong>{{ sourceTypeLabel(detail.source_type) }}</strong></div>
              <div><span>From</span><strong>{{ originalEmail(detail).sender_name || detail.sender_name || '-' }}</strong></div>
              <div><span>Sender email</span><strong>{{ originalEmail(detail).sender_email || detail.sender_email || '-' }}</strong></div>
              <div><span>Original sent at</span><strong>{{ formatDate(originalEmail(detail).sent_at || originalEmail(detail).sent_at_raw || detail.sent_at) }}</strong></div>
              <div><span>Received by mailbox</span><strong>{{ formatDate(mailReceivedAt(detail)) }}</strong></div>
              <div><span>Evidence #</span><strong>#{{ detail.source_evidence_id || '-' }}</strong></div>
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
              <div class="text-caption text-grey-7 q-mt-sm">The forwarded message is retained as mailbox evidence; extraction uses the original business message.</div>
            </div>
          </div>
          <div class="source-intake-section-title">Business Link</div>
          <div class="source-intake-detail-grid">
            <div><span>Matched entity</span><strong>{{ detail.matched_entity_type || '-' }}</strong></div>
            <div><span>Entity reference</span><strong>{{ detail.matched_entity_ref || '-' }}</strong></div>
            <div><span>Owner role</span><strong>{{ ownerRoleLabel(detail.owner_role) }}</strong></div>
            <div><span>Classification confidence</span><strong>{{ confidenceLabel(detail.classification_confidence) }}</strong></div>
          </div>
          <div class="source-intake-field-label q-mt-md">Next action</div>
          <div class="text-weight-medium q-mb-sm">{{ nextActionLabel(detail) }}</div>
          <div class="source-intake-field-label">Instructions</div>
          <div class="q-mb-md source-intake-wrap">{{ rawNextAction(detail) || '-' }}</div>
          <div v-if="detail.exception_summary" class="source-intake-exception q-pa-sm q-mb-md">
            <div class="text-weight-medium q-mb-xs"><q-icon name="warning" /> Exception</div>
            <div>{{ detail.exception_summary }}</div>
          </div>
          <div class="source-intake-section-title">Information from email</div>
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
import { getauth, postauth } from 'boot/axios_request.js'
import GreaterWmsOperationsTable from 'components/GreaterWmsOperationsTable.vue'
import { isMail2TaskPreview } from 'src/utils/mail2taskPreview'

const MAIL_TASK_NEXT_ACTIONS = Object.freeze({
  PREPARE_WMS: Object.freeze({ label: 'Prepare WMS', owner: 'Maggie' }),
  APPROVE_OUTBOUND: Object.freeze({ label: 'Approve outbound', owner: 'Sunny' }),
  START_SITE: Object.freeze({ label: 'Start site work', owner: 'Mark' }),
  COMPLETE_SITE: Object.freeze({ label: 'Complete site work', owner: 'Mark' }),
  COMPLETE_WMS: Object.freeze({ label: 'Update WMS', owner: 'Maggie' }),
  RESOLVE_EXCEPTION: Object.freeze({ label: 'Resolve exception', owner: 'Sunny' }),
  COMPLETE: Object.freeze({ label: 'Complete', owner: '' }),
  REVIEW: Object.freeze({ label: 'Review', owner: 'Sunny' })
})

const MAIL_TASK_STATUS_NEXT_ACTIONS = Object.freeze({
  OPEN: 'PREPARE_WMS',
  AWAITING_SUNNY_APPROVAL: 'APPROVE_OUTBOUND',
  READY_FOR_MARK: 'START_SITE',
  SITE_IN_PROGRESS: 'COMPLETE_SITE',
  WMS_FINALIZATION: 'COMPLETE_WMS',
  COMPLETED: 'COMPLETE',
  BLOCKED: 'RESOLVE_EXCEPTION'
})

export default {
  name: 'SourceIntake',
  components: { GreaterWmsOperationsTable },
  data () {
    return {
      loading: false,
      previewMode: isMail2TaskPreview(),
      rows: [],
      detail: null,
      detailOpen: false,
      status: '',
      operation: '',
      taskStatus: '',
      search: '',
      counts: {},
      taskCounts: {},
      total: 0,
      hasMore: false,
      pagination: { rowsPerPage: 0 },
      offset: 0,
      actors: [],
      assignmentRole: 'WMS_OPERATOR',
      assignmentStaffId: null,
      wmsEntitySystem: '',
      wmsEntityRef: '',
      wmsHandoffNote: '',
      actionLoading: false,
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
      taskStatusOptions: [
        { label: 'Open · Maggie', value: 'OPEN' },
        { label: 'Awaiting Sunny approval', value: 'AWAITING_SUNNY_APPROVAL' },
        { label: 'Ready · Mark', value: 'READY_FOR_MARK' },
        { label: 'Site work · Mark', value: 'SITE_IN_PROGRESS' },
        { label: 'WMS update · Maggie', value: 'WMS_FINALIZATION' },
        { label: 'Completed', value: 'COMPLETED' },
        { label: 'Blocked · Sunny review', value: 'BLOCKED' }
      ],
      taskRoleOptions: [
        { label: 'Sunny / Supervisor', value: 'SUPERVISOR' },
        { label: 'Maggie / WMS operator', value: 'WMS_OPERATOR' },
        { label: 'Mark / Site operator', value: 'SITE_OPERATOR' }
      ],
      wmsSystemOptions: [
        { label: 'Legacy production', value: 'LEGACY_PROD' },
        { label: 'Migrated GreaterWMS', value: 'MIGRATED' }
      ],
      columns: [
        { name: 'status', label: 'Task / Mail', field: 'task_status', align: 'left', style: 'min-width: 120px; width: 135px; max-width: 160px;', headerStyle: 'min-width: 120px; width: 135px; max-width: 160px;' },
        { name: 'task', label: 'Task', field: 'task_id', align: 'left', style: 'min-width: 130px; width: 150px; max-width: 170px;', headerStyle: 'min-width: 130px; width: 150px; max-width: 170px;' },
        { name: 'reference', label: 'Ref / Type', field: 'external_reference', align: 'left', style: 'min-width: 105px; width: 120px; max-width: 140px;', headerStyle: 'min-width: 105px; width: 120px; max-width: 140px;' },
        { name: 'next_action', label: 'Next', field: 'task_next_action', align: 'left', style: 'min-width: 110px; width: 130px; max-width: 160px;', headerStyle: 'min-width: 110px; width: 130px; max-width: 160px;' },
        { name: 'owner', label: 'Owner', field: 'assigned_role', align: 'left', style: 'min-width: 75px; width: 90px; max-width: 110px;', headerStyle: 'min-width: 75px; width: 90px; max-width: 110px;' },
        { name: 'source', label: 'Source', field: 'sender_email', align: 'left', style: 'min-width: 110px; width: 125px; max-width: 150px;', headerStyle: 'min-width: 110px; width: 125px; max-width: 150px;' },
        { name: 'received_at', label: 'Sent / Recv', field: 'sent_at', align: 'left', style: 'min-width: 95px; width: 105px; max-width: 120px;', headerStyle: 'min-width: 95px; width: 105px; max-width: 120px;' },
        { name: 'action', label: '', field: 'action', align: 'right' }
      ]
    }
  },
  computed: {
    countItems () {
      const statuses = [
        { key: 'OPEN', label: 'Open' },
        { key: 'AWAITING_SUNNY_APPROVAL', label: 'Sunny approval' },
        { key: 'READY_FOR_MARK', label: 'Ready for Mark' },
        { key: 'SITE_IN_PROGRESS', label: 'Mark in progress' },
        { key: 'WMS_FINALIZATION', label: 'Maggie WMS' },
        { key: 'COMPLETED', label: 'Completed' },
        { key: 'BLOCKED', label: 'Blocked' }
      ]
      return [{ key: '__TOTAL__', label: 'Tasks', color: 'grey-8', value: this.taskTotal }].concat(
        statuses
          .filter(item => Number(this.taskCounts[item.key] || 0) > 0)
          .map(item => ({ ...item, color: this.taskStatusColor(item.key), value: this.taskCounts[item.key] }))
      )
    },
    taskTotal () {
      return Object.values(this.taskCounts).reduce((total, value) => total + Number(value || 0), 0)
    },
    actorOptions () {
      return this.actors
        .filter(item => (item.task_roles || []).includes(this.assignmentRole))
        .map(item => ({ label: `${item.name} · ${item.staff_type}`, value: item.id }))
    },
    extractionRows () {
      if (!this.detail) return []
      const items = (this.detail.extractions || []).map((item, index) => ({
        key: `extraction-${index}-${item.field_name}`,
        label: this.fieldLabel(item.field_name),
        value: this.displayFieldValue(item.field_name, item.normalized_value || item.raw_value || '-'),
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
        value: this.displayFieldValue(key, metadata[key]),
        source_location: 'Email metadata',
        confidence: '',
        flags: ''
      }))
    }
  },
  mounted () {
    if (this.previewMode) {
      this.loadPreview()
    } else {
      this.load()
    }
  },
  methods: {
    queryString (offset) {
      const params = new URLSearchParams()
      params.set('limit', '50')
      params.set('offset', String(offset))
      if (this.status) params.set('status', this.status)
      if (this.operation) params.set('operation', this.operation)
      if (this.taskStatus) params.set('task_status', this.taskStatus)
      if (this.search) params.set('q', this.search)
      return `asn/serial/intake/?${params.toString()}`
    },
    previewRows () {
      return [
        {
          id: 9001,
          task_id: 9001,
          task_ref: 'IB-TRHU4217950',
          subject: 'Inbound notice · TRHU4217950',
          sent_at: '2026-08-25T09:15:00Z',
          received_at_raw: '2026-08-25T09:16:00Z',
          captured_at: '2026-08-25T09:17:00Z',
          document_type: 'INBOUND_NOTICE',
          sender_name: 'Delta Logistics',
          sender_email: 'delta-logistics@example.com',
          external_reference: 'TRHU4217950',
          operation: 'INBOUND',
          task_status: 'READY_FOR_MARK',
          status: 'READY_FOR_PREVIEW',
          assigned_role: 'SITE_OPERATOR',
          assigned_role_label: 'Mark / Site operator',
          assigned_staff_id: 3003,
          assigned_staff_name: 'Mark',
          wms_handoff_status: 'TO_MARK',
          wms_handoff_label: 'To Mark · site execution',
          task_next_action: 'Mark: confirm physical receipt',
          next_action: 'Mark verifies cartons and records any variance.',
          next_action_label: 'Mark: confirm physical receipt',
          task_email_count: 2,
          source_evidence_id: 7001,
          matched_entity_type: 'ASN',
          matched_entity_ref: 'ASN-20260825-0042',
          email_body_preview: 'Please confirm receipt for container TRHU4217950.',
          exception_summary: ''
        },
        {
          id: 9002,
          task_id: 9002,
          task_ref: 'OB-TRLU9821043',
          subject: 'Outbound delivery request · BOL attached',
          sent_at: '2026-08-25T10:40:00Z',
          received_at_raw: '2026-08-25T10:41:00Z',
          captured_at: '2026-08-25T10:42:00Z',
          document_type: 'DELIVERY_REQUEST',
          sender_name: 'Delta Forwarder',
          sender_email: 'forwarder@example.com',
          external_reference: 'TRLU9821043',
          operation: 'OUTBOUND',
          task_status: 'AWAITING_SUNNY_APPROVAL',
          status: 'APPROVAL_REQUIRED',
          assigned_role: 'SUPERVISOR',
          assigned_role_label: 'Sunny / Supervisor',
          assigned_staff_id: 3001,
          assigned_staff_name: 'Sunny',
          wms_handoff_status: 'TO_SUNNY',
          wms_handoff_label: 'To Sunny · outbound approval',
          task_next_action: 'Sunny: approve outbound request',
          next_action: 'Sunny confirms the outbound request before Mark starts site work.',
          next_action_label: 'Sunny: approve outbound request',
          task_email_count: 1,
          source_evidence_id: 7002,
          matched_entity_type: 'DN',
          matched_entity_ref: 'DN-20260825-0017',
          email_body_preview: 'Please approve the attached BOL and release the outbound order.',
          exception_summary: ''
        }
      ]
    },
    previewActors () {
      return [
        { id: 3001, name: 'Sunny', staff_type: 'Supervisor', task_roles: ['SUPERVISOR'] },
        { id: 3002, name: 'Maggie', staff_type: 'Warehouse', task_roles: ['WMS_OPERATOR'] },
        { id: 3003, name: 'Mark', staff_type: 'Warehouse', task_roles: ['SITE_OPERATOR'] }
      ]
    },
    previewTaskActions (status) {
      return {
        OPEN: [{ code: 'PREPARE_WMS', label: 'Prepare WMS handoff' }, { code: 'BLOCK', label: 'Block task' }],
        AWAITING_SUNNY_APPROVAL: [{ code: 'APPROVE_OUTBOUND', label: 'Approve outbound' }, { code: 'REJECT_OUTBOUND', label: 'Reject outbound' }, { code: 'BLOCK', label: 'Block task' }],
        READY_FOR_MARK: [{ code: 'START_SITE', label: 'Start site work' }, { code: 'BLOCK', label: 'Block task' }],
        SITE_IN_PROGRESS: [{ code: 'COMPLETE_SITE', label: 'Complete site work' }, { code: 'BLOCK', label: 'Block task' }],
        WMS_FINALIZATION: [{ code: 'COMPLETE_WMS', label: 'Complete WMS handoff' }, { code: 'BLOCK', label: 'Block task' }],
        COMPLETED: [],
        BLOCKED: [{ code: 'REOPEN', label: 'Reopen task' }]
      }[status] || []
    },
    loadPreview () {
      const sourceRows = this.previewRows()
      const filteredRows = sourceRows.filter(row => {
        const matchesStatus = !this.status || row.status === this.status
        const matchesOperation = !this.operation || row.operation === this.operation
        const matchesTaskStatus = !this.taskStatus || row.task_status === this.taskStatus
        const haystack = [row.task_id, row.task_ref, row.subject, row.sender_name, row.sender_email, row.external_reference, row.task_next_action].join(' ').toLowerCase()
        const matchesSearch = !this.search || haystack.includes(String(this.search).toLowerCase())
        return matchesStatus && matchesOperation && matchesTaskStatus && matchesSearch
      })
      this.rows = filteredRows
      this.counts = {}
      this.taskCounts = filteredRows.reduce((counts, row) => {
        counts[row.task_status] = (counts[row.task_status] || 0) + 1
        return counts
      }, {})
      this.total = filteredRows.length
      this.hasMore = false
      this.offset = 0
    },
    load () {
      if (this.previewMode) {
        this.loadPreview()
        return
      }
      this.loading = true
      this.offset = 0
      getauth(this.queryString(0))
        .then(res => {
          this.rows = res.items || []
          this.counts = res.counts || {}
          this.taskCounts = res.task_counts || {}
          this.total = Number(res.total || 0)
          this.hasMore = Boolean(res.has_more)
        })
        .catch(() => {})
        .finally(() => { this.loading = false })
    },
    loadMore () {
      if (this.previewMode) return
      this.loading = true
      const nextOffset = this.rows.length
      getauth(this.queryString(nextOffset))
        .then(res => {
          this.rows = this.rows.concat(res.items || [])
          this.counts = res.counts || this.counts
          this.taskCounts = res.task_counts || this.taskCounts
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
      this.assignmentRole = 'WMS_OPERATOR'
      this.assignmentStaffId = null
      this.wmsEntitySystem = ''
      this.wmsEntityRef = ''
      this.wmsHandoffNote = ''
      if (this.previewMode) {
        this.loadActors()
        this.detail = this.previewDetail(id)
        if (this.detail) {
          this.assignmentRole = this.detail.assigned_role || 'WMS_OPERATOR'
          this.assignmentStaffId = this.detail.assigned_staff_id || null
        }
        return
      }
      this.loadActors()
      getauth(`asn/serial/intake/${id}/`).then(res => {
        this.detail = res
        this.assignmentRole = res.assigned_role || 'WMS_OPERATOR'
        this.assignmentStaffId = res.assigned_staff_id || null
        this.wmsEntitySystem = res.wms_entity_system || ''
        this.wmsEntityRef = res.wms_entity_ref || ''
        this.wmsHandoffNote = ''
      }).catch(() => {})
    },
    loadActors () {
      if (this.previewMode) {
        this.actors = this.previewActors()
        return
      }
      getauth('asn/serial/intake/task-actors/')
        .then(res => { this.actors = res.results || [] })
        .catch(() => {})
    },
    previewDetail (id) {
      const row = this.previewRows().find(item => item.id === id)
      if (!row) return null
      const isOutbound = row.operation === 'OUTBOUND'
      return {
        ...row,
        task_actions: this.previewTaskActions(row.task_status),
        approvals: isOutbound ? [{ id: 8002, status: 'PENDING', requested_by_name: 'Mail2Task', requested_at: '2026-08-25T10:42:00Z', note: 'Sunny final approval is required before site release.' }] : [],
        task_events: [
          { id: 8100 + id, action: 'CREATED', actor_name: 'Mail2Task', created_at: '2026-08-25T09:17:00Z', note: 'Created from source email and grouped by business reference.', to_status: 'OPEN' },
          { id: 8200 + id, action: isOutbound ? 'PREPARE_WMS' : 'PREPARE_WMS', actor_name: 'Maggie', created_at: '2026-08-25T10:00:00Z', note: isOutbound ? 'WMS handoff prepared; waiting for Sunny approval.' : 'WMS handoff prepared; site work assigned to Mark.', to_status: row.task_status }
        ],
        source_type: 'EMAIL',
        original_email: {
          sender_name: row.sender_name,
          sender_email: row.sender_email,
          sent_at: row.sent_at,
          sent_at_raw: row.sent_at,
          message_id: `<preview-${row.id}@mail2task.local>`,
          thread_id: `preview-thread-${row.id}`,
          from_raw: `${row.sender_name} <${row.sender_email}>`,
          to: ['sunny@peaksmartlogistics.com', 'maggie@peaksmartlogistics.com'],
          cc: [],
          subject: row.subject
        },
        email_body: row.email_body_preview,
        metadata: { external_reference: row.external_reference, business_operation: row.operation, container_no: row.external_reference },
        extractions: [
          { field_name: 'external_reference', normalized_value: row.external_reference, confidence: 0.98, source_location: 'Subject / attachment', human_confirmed: true, used_for_write: false },
          { field_name: 'business_operation', normalized_value: row.operation, confidence: 0.97, source_location: 'Email classification', human_confirmed: true, used_for_write: false }
        ],
        attachments: [{ id: 8300 + id, attachment_name: isOutbound ? 'BOL-TRLU9821043.pdf' : 'packing-list-TRHU4217950.pdf', content_type: 'application/pdf', security_status: 'SAFE', storage_size: 184320, source_location: 'Mail2Task preview fixture' }],
        storage_uri: 'preview://mail2task/evidence',
        storage_size: 184320,
        content_hash: `previewhash${row.id}000000000000`,
        owner_role: row.assigned_role,
        classification_confidence: 0.97,
        events: [{ id: 8400 + id, event_type: 'CAPTURED', created_at: '2026-08-25T09:17:00Z', message: 'Source email captured for local preview.', status: 'CAPTURED' }]
      }
    },
    updatePreviewRow (detail) {
      const index = this.rows.findIndex(row => row.id === detail.id)
      if (index >= 0) this.$set(this.rows, index, { ...this.rows[index], ...detail })
      this.taskCounts = this.rows.reduce((counts, row) => {
        counts[row.task_status] = (counts[row.task_status] || 0) + 1
        return counts
      }, {})
    },
    previewAssignmentLabel (role) {
      return { SUPERVISOR: 'Sunny / Supervisor', WMS_OPERATOR: 'Maggie / WMS operator', SITE_OPERATOR: 'Mark / Site operator' }[role] || role
    },
    applyPreviewAssignment () {
      const actor = this.actors.find(item => String(item.id) === String(this.assignmentStaffId))
      const role = this.assignmentRole
      const roleName = actor ? actor.name : ''
      this.detail.assigned_role = role
      this.detail.assigned_role_label = this.previewAssignmentLabel(role)
      this.detail.assigned_staff_id = actor ? actor.id : null
      this.detail.assigned_staff_name = roleName
      this.detail.owner_role = role
      this.detail.task_events = (this.detail.task_events || []).concat([{ id: Date.now(), action: 'ASSIGN', actor_name: 'Preview user', created_at: new Date().toISOString(), note: `Assigned to ${roleName || this.previewAssignmentLabel(role)}.`, to_status: this.detail.task_status }])
      this.updatePreviewRow(this.detail)
      this.$q.notify({ message: 'Preview only: assignment changed locally', icon: 'visibility', color: 'info' })
    },
    applyPreviewAction (action) {
      const transitions = {
        PREPARE_WMS: { status: 'READY_FOR_MARK', role: 'SITE_OPERATOR', staff: 'Mark', handoff: 'TO_MARK', handoffLabel: 'To Mark · site execution', next: 'Mark: confirm physical receipt', emailStatus: 'READY_FOR_PREVIEW' },
        APPROVE_OUTBOUND: { status: 'READY_FOR_MARK', role: 'SITE_OPERATOR', staff: 'Mark', handoff: 'TO_MARK', handoffLabel: 'To Mark · site execution', next: 'Mark: confirm physical receipt', emailStatus: 'READY_FOR_PREVIEW' },
        START_SITE: { status: 'SITE_IN_PROGRESS', role: 'SITE_OPERATOR', staff: 'Mark', handoff: 'SITE_IN_PROGRESS', handoffLabel: 'Mark · site work in progress', next: 'Mark: complete site work', emailStatus: 'EXECUTING' },
        COMPLETE_SITE: { status: 'WMS_FINALIZATION', role: 'WMS_OPERATOR', staff: 'Maggie', handoff: 'RETURNED_TO_MAGGIE', handoffLabel: 'Returned to Maggie · WMS update', next: 'Maggie: update WMS and record reference', emailStatus: 'EXECUTING' },
        COMPLETE_WMS: { status: 'COMPLETED', role: 'WMS_OPERATOR', staff: 'Maggie', handoff: 'COMPLETED', handoffLabel: 'WMS handoff completed', next: 'No further action', emailStatus: 'COMPLETED' },
        REJECT_OUTBOUND: { status: 'BLOCKED', role: 'SUPERVISOR', staff: 'Sunny', handoff: 'BLOCKED', handoffLabel: 'Blocked · Sunny review', next: 'Sunny: resolve exception and reopen', emailStatus: 'BLOCKED' },
        BLOCK: { status: 'BLOCKED', role: 'SUPERVISOR', staff: 'Sunny', handoff: 'BLOCKED', handoffLabel: 'Blocked · Sunny review', next: 'Sunny: resolve exception and reopen', emailStatus: 'BLOCKED' },
        REOPEN: { status: 'OPEN', role: 'WMS_OPERATOR', staff: 'Maggie', handoff: 'TO_MAGGIE', handoffLabel: 'To Maggie · prepare WMS', next: 'Maggie: prepare WMS handoff', emailStatus: 'CAPTURED' }
      }[action]
      if (!transitions) return
      const next = transitions
      const actor = this.actors.find(item => item.name === next.staff)
      this.detail.task_status = next.status
      this.detail.status = next.emailStatus
      this.detail.assigned_role = next.role
      this.detail.assigned_role_label = this.previewAssignmentLabel(next.role)
      this.detail.assigned_staff_id = actor ? actor.id : null
      this.detail.assigned_staff_name = next.staff
      this.detail.owner_role = next.role
      this.detail.wms_handoff_status = next.handoff
      this.detail.wms_handoff_label = next.handoffLabel
      this.detail.task_next_action = next.next
      this.detail.next_action_label = next.next
      this.detail.next_action = next.next
      this.detail.task_actions = this.previewTaskActions(next.status)
      if (action === 'APPROVE_OUTBOUND' && this.detail.approvals && this.detail.approvals[0]) {
        this.detail.approvals[0].status = 'APPROVED'
        this.detail.approvals[0].decided_by_name = 'Sunny'
        this.detail.approvals[0].decided_at = new Date().toISOString()
      }
      this.detail.task_events = (this.detail.task_events || []).concat([{ id: Date.now(), action, actor_name: next.staff, created_at: new Date().toISOString(), note: `Preview transition: ${next.next}.`, to_status: next.status }])
      this.updatePreviewRow(this.detail)
      this.assignmentRole = next.role
      this.assignmentStaffId = actor ? actor.id : null
      this.$q.notify({ message: `Preview only: ${action} applied locally`, icon: 'visibility', color: 'info' })
    },
    assignTask () {
      if (!this.detail || !this.detail.task_id || !this.assignmentRole) return
      if (this.previewMode) {
        this.applyPreviewAssignment()
        return
      }
      this.actionLoading = true
      postauth(`asn/serial/intake/${this.detail.task_id}/assign/`, {
        assigned_role: this.assignmentRole,
        staff_id: this.assignmentStaffId || null
      })
        .then(() => {
          this.$q.notify({ message: 'Task assignment updated', icon: 'check', color: 'positive' })
          this.showDetail(this.detail.id)
          this.load()
        })
        .catch(() => {})
        .finally(() => { this.actionLoading = false })
    },
    performTaskAction (action) {
      if (!this.detail || !this.detail.task_id) return
      if (this.previewMode) {
        this.applyPreviewAction(action)
        return
      }
      this.actionLoading = true
      postauth(`asn/serial/intake/${this.detail.task_id}/action/`, {
        action,
        wms_entity_system: this.wmsEntitySystem || '',
        wms_entity_ref: this.wmsEntityRef || '',
        note: this.wmsHandoffNote || ''
      })
        .then(() => {
          this.$q.notify({ message: 'Task handoff recorded', icon: 'check', color: 'positive' })
          this.showDetail(this.detail.id)
          this.load()
        })
        .catch(() => {})
        .finally(() => { this.actionLoading = false })
    },
    formatDate (value) {
      return value ? String(value).replace('T', ' ').slice(0, 16) : '-'
    },
    taskDisplayRef (row) {
      if (!row) return '-'
      const taskId = row.task_id
      if (taskId !== null && taskId !== undefined && taskId !== '') {
        return `MT-${String(taskId).padStart(4, '0')}`
      }
      return row.id ? `MAIL-${row.id}` : 'MAIL-—'
    },
    formatSourceTime (value) {
      return value ? this.formatDate(value) : 'Not provided'
    },
    compactSourceTime (value) {
      if (!value) return '-'
      const raw = String(value).trim()
      const isoLike = raw.match(/^(\d{4})[-/]?(\d{2})[-/]?(\d{2})[ T](\d{1,2}):(\d{2})/)
      const chineseLike = raw.match(/^(\d{4})年(\d{1,2})月(\d{1,2})日(?:[ T]?(\d{1,2}):(\d{2}))?/)
      const monthFirst = raw.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?:[ T](\d{1,2}):(\d{2}))?/)
      const match = isoLike || chineseLike
      if (match) {
        const month = match === isoLike ? match[2] : String(match[2]).padStart(2, '0')
        const day = match === isoLike ? match[3] : String(match[3]).padStart(2, '0')
        const hour = String(match[4] || '00').padStart(2, '0')
        const minute = match[5] || '00'
        return `${month}/${day} ${hour}:${minute}`
      }
      if (monthFirst) {
        return `${String(monthFirst[1]).padStart(2, '0')}/${String(monthFirst[2]).padStart(2, '0')} ${String(monthFirst[4] || '00').padStart(2, '0')}:${monthFirst[5] || '00'}`
      }
      return '-'
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
    referenceTooltip (row) {
      const reference = row.external_reference || row.matched_entity_ref || '-'
      const preview = String(row.email_body_preview || '').trim()
      return preview ? `Reference: ${reference}\nEmail: ${preview}` : `Reference: ${reference}`
    },
    referenceTypeTooltip (row) {
      if (!row) return 'No reference or type recorded'
      return [
        `Operation: ${this.operationLabel(row.operation)}`,
        `Document: ${this.documentLabel(row.document_type)}`,
        this.referenceTooltip(row)
      ].join('\n')
    },
    compactSubject (value) {
      const subject = String(value || 'No subject')
      return subject.length <= 28 ? subject : `${subject.slice(0, 25)}…`
    },
    compactReference (value) {
      const reference = String(value || '').trim()
      if (!reference) return '-'
      if (reference.length <= 14) return reference
      const po = reference.match(/^PO#?\s*(\d+)$/i)
      if (po) return `PO…${po[1].slice(-4)}`
      const mawb = reference.match(/^\d{3}[- ]?(\d{8})$/)
      if (mawb) return `MAWB…${mawb[1].slice(-4)}`
      const prefixed = reference.match(/^([A-Za-z]{2,8})[- ]?(.+)$/)
      if (prefixed) {
        const suffix = prefixed[2].replace(/[^A-Za-z0-9]/g, '')
        return `${prefixed[1].toUpperCase()}…${suffix.slice(-4)}`
      }
      return `${reference.slice(0, 5)}…${reference.slice(-4)}`
    },
    compactEntity (row) {
      if (!row || !row.matched_entity_ref) return 'Matched'
      return `${row.matched_entity_type || 'WMS'} ${this.compactReference(row.matched_entity_ref)}`
    },
    originalEmail (detail) {
      return (detail && detail.original_email) || {}
    },
    forwardedEmail (detail) {
      return (detail && detail.forwarded_email) || {}
    },
    mailReceivedAt (detail) {
      if (!detail) return ''
      const original = this.originalEmail(detail)
      const forwarded = this.forwardedEmail(detail)
      return original.received_at || detail.received_at || detail.received_at_raw || forwarded.received_at || ''
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
        READY_FOR_PREVIEW: 'Ready for review',
        APPROVAL_REQUIRED: 'Approval needed',
        EXECUTING: 'Executing',
        COMPLETED: 'Completed',
        BLOCKED: 'Blocked',
        DUPLICATE: 'Duplicate',
        FAILED: 'Failed'
      }[value] || value || 'Unknown'
    },
    statusShortLabel (value) {
      return {
        CAPTURED: 'Captured',
        ANALYZING: 'Analyzing',
        REVIEW_REQUIRED: 'Review',
        READY_FOR_PREVIEW: 'Review ready',
        APPROVAL_REQUIRED: 'Need approval',
        EXECUTING: 'Executing',
        COMPLETED: 'Done',
        BLOCKED: 'Blocked',
        DUPLICATE: 'Duplicate',
        FAILED: 'Failed'
      }[value] || value || 'Unknown'
    },
    operationLabel (value) {
      return { INBOUND: 'Inbound', OUTBOUND: 'Outbound', SUPPORTING: 'Supporting', TRANSFER: 'Transfer', UNKNOWN: 'Unknown' }[value] || value || '-'
    },
    operationShortLabel (value) {
      return { INBOUND: 'IB', OUTBOUND: 'OB', SUPPORTING: 'SUP', TRANSFER: 'TR', UNKNOWN: '-' }[value] || value || '-'
    },
    ownerLabel (value) {
      return String(value || '').trim() || 'Unassigned'
    },
    ownerRoleLabel (value) {
      return {
        SUPERVISOR: 'Sunny / Supervisor',
        WMS_OPERATOR: 'Maggie / WMS operator',
        SITE_OPERATOR: 'Mark / Site operator'
      }[value] || String(value || '').trim() || 'Unassigned'
    },
    taskStatusLabel (value) {
      return {
        OPEN: 'Open · Maggie',
        AWAITING_SUNNY_APPROVAL: 'Awaiting Sunny approval',
        READY_FOR_MARK: 'Ready · Mark',
        SITE_IN_PROGRESS: 'Site work · Mark',
        WMS_FINALIZATION: 'WMS update · Maggie',
        COMPLETED: 'Completed',
        BLOCKED: 'Blocked · Sunny review'
      }[value] || value || 'Unknown'
    },
    taskStatusShortLabel (value) {
      return {
        OPEN: 'Open',
        AWAITING_SUNNY_APPROVAL: 'Need Sunny',
        READY_FOR_MARK: 'Ready / Mark',
        SITE_IN_PROGRESS: 'Mark working',
        WMS_FINALIZATION: 'Maggie WMS',
        COMPLETED: 'Done',
        BLOCKED: 'Blocked'
      }[value] || value || 'Unknown'
    },
    taskStatusColor (value) {
      return {
        OPEN: 'blue-grey-7',
        AWAITING_SUNNY_APPROVAL: 'orange-8',
        READY_FOR_MARK: 'teal-7',
        SITE_IN_PROGRESS: 'indigo-7',
        WMS_FINALIZATION: 'blue-8',
        COMPLETED: 'positive',
        BLOCKED: 'negative'
      }[value] || this.statusColor(value)
    },
    wmsHandoffLabel (row) {
      if (row && row.wms_handoff_label) return row.wms_handoff_label
      if (row && row.matched_entity_ref) {
        return `${row.matched_entity_type || 'WMS'}: ${row.matched_entity_ref}`
      }
      return 'WMS handoff pending'
    },
    wmsHandoffShortLabel (row) {
      const status = row && row.wms_handoff_status
      return {
        TO_SUNNY: 'To Sunny',
        TO_MAGGIE: 'To Maggie',
        TO_MARK: 'To Mark',
        SITE_IN_PROGRESS: 'Mark working',
        RETURNED_TO_MAGGIE: 'Back to Maggie',
        COMPLETED: 'WMS done',
        BLOCKED: 'Blocked'
      }[status] || (row && row.matched_entity_ref ? 'WMS matched' : 'WMS pending')
    },
    wmsHandoffTooltip (row) {
      if (row && row.wms_handoff_label) {
        return `${row.wms_handoff_label}${row.wms_entity_ref ? ` · ${row.wms_entity_ref}` : ''}`
      }
      return row && row.matched_entity_ref
        ? `Matched WMS entity: ${row.matched_entity_type || 'WMS'} ${row.matched_entity_ref}`
        : 'No WMS entity has been matched yet.'
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
    documentShortLabel (value) {
      return {
        INBOUND_NOTICE: 'A/N',
        PACK_LIST: 'PL',
        PICK_TICKET: 'Pick',
        DELIVERY_REQUEST: 'DO',
        APPOINTMENT: 'Appt',
        QC_SCAN: 'QC',
        OTHER: 'Other'
      }[value] || value || 'Other'
    },
    sourceTypeLabel (value) {
      return { EMAIL: 'Email', AI_AGENT: 'AI agent', WEB_FORM: 'Web form', CLI: 'CLI' }[value] || value || 'Source'
    },
    ownerShortLabel (row) {
      if (row && row.assigned_staff_name) return row.assigned_staff_name
      return { SUPERVISOR: 'Sunny', WMS_OPERATOR: 'Maggie', SITE_OPERATOR: 'Mark' }[row && row.assigned_role] || 'Unassigned'
    },
    rawNextAction (row) {
      if (!row) return ''
      return String(row.task_next_action || row.next_action || row.next_action_label || (row.exception_summary ? 'Review exception' : '')).trim()
    },
    nextActionDescriptor (row) {
      const item = row || {}
      const explicitCode = String(item.task_next_action_code || '').trim().toUpperCase()
      if (MAIL_TASK_NEXT_ACTIONS[explicitCode]) {
        return { code: explicitCode, ...MAIL_TASK_NEXT_ACTIONS[explicitCode] }
      }

      const statusCode = String(item.task_status || '').trim().toUpperCase()
      const statusAction = statusCode === 'OPEN' && String(item.assigned_role || '').toUpperCase() === 'SUPERVISOR'
        ? 'REVIEW'
        : MAIL_TASK_STATUS_NEXT_ACTIONS[statusCode]
      if (statusAction && MAIL_TASK_NEXT_ACTIONS[statusAction]) {
        return { code: statusAction, ...MAIL_TASK_NEXT_ACTIONS[statusAction] }
      }

      const instruction = this.rawNextAction(item).toLowerCase()
      let inferredCode = ''
      if (instruction.includes('approve') && instruction.includes('outbound')) {
        inferredCode = 'APPROVE_OUTBOUND'
      } else if (instruction.includes('no further action') || ['complete', 'completed'].includes(instruction)) {
        inferredCode = 'COMPLETE'
      } else if (['resolve exception', 'clarify', 'request clarification', 'reopen'].some(token => instruction.includes(token))) {
        inferredCode = 'RESOLVE_EXCEPTION'
      } else if (instruction.includes('complete') && (instruction.includes('site') || instruction.includes('physical'))) {
        inferredCode = 'COMPLETE_SITE'
      } else if (instruction.includes('prepare') && instruction.includes('wms')) {
        inferredCode = 'PREPARE_WMS'
      } else if (instruction.includes('wms') && ['record', 'update', 'close', 'complete'].some(token => instruction.includes(token))) {
        inferredCode = 'COMPLETE_WMS'
      } else if (['physical receiving', 'site movement', 'site work', 'confirm physical receipt'].some(token => instruction.includes(token))) {
        inferredCode = 'START_SITE'
      }

      const code = inferredCode || 'REVIEW'
      return { code, ...MAIL_TASK_NEXT_ACTIONS[code] }
    },
    nextActionLabel (row) {
      return this.nextActionDescriptor(row).label
    },
    nextActionTooltip (row) {
      const action = this.nextActionDescriptor(row)
      const detail = this.rawNextAction(row)
      return [
        `Next: ${action.label}`,
        action.owner ? `Role: ${action.owner}` : '',
        detail ? `Instruction: ${detail}` : ''
      ].filter(Boolean).join('\n')
    },
    confidenceLabel (value) {
      if (value === null || value === undefined || value === '') return 'Not recorded'
      const numeric = Number(value)
      return Number.isNaN(numeric) ? String(value) : `${Math.round(numeric * 100)}%`
    },
    approvalStatusLabel (value) {
      return { PENDING: 'Pending', APPROVED: 'Approved', REJECTED: 'Rejected', CANCELLED: 'Cancelled' }[value] || this.statusLabel(value)
    },
    displayFieldValue (field, value) {
      if (value === null || value === undefined || value === '') return '-'
      const key = String(field || '').trim().toLowerCase()
      if (key === 'business_operation' || key === 'operation') return this.operationLabel(value)
      if (key === 'owner_role') return this.ownerRoleLabel(value)
      return this.formatValue(value)
    },
    fieldLabel (value) {
      const key = String(value || '').trim().toLowerCase()
      const labels = {
        external_reference: 'External reference',
        business_operation: 'Operation',
        container_no: 'Container',
        eta: 'ETA',
        mawb: 'MAWB',
        hawb: 'HAWB',
        bol: 'BOL',
        bol_number: 'BOL number',
        do: 'DO',
        do_number: 'DO number',
        po: 'PO',
        dn: 'DN',
        sku: 'SKU',
        customer_address: 'Customer address',
        receiving_address: 'Receiving address',
        requested_delivery_date: 'Requested delivery date'
      }
      if (labels[key]) return labels[key]
      return key.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()) || 'Field'
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
      const key = String(value || '').trim().toUpperCase()
      const labels = {
        CREATED: 'Created',
        ASSIGN: 'Assigned',
        START_SITE: 'Site work started',
        COMPLETE_SITE: 'Site work completed',
        COMPLETE_WMS: 'WMS handoff completed',
        APPROVE_OUTBOUND: 'Outbound approved',
        REJECT_OUTBOUND: 'Outbound rejected',
        PREPARE_WMS: 'WMS handoff prepared',
        ORIGINAL_EMAIL_RECONCILED: 'Original email reconciled',
        CAPTURED: 'Captured',
        ANALYZING: 'Analyzing',
        REVIEW_REQUIRED: 'Review required',
        READY_FOR_PREVIEW: 'Ready for review',
        APPROVAL_REQUIRED: 'Approval needed',
        EXECUTING: 'Executing',
        COMPLETED: 'Completed',
        BLOCKED: 'Blocked',
        DUPLICATE: 'Duplicate',
        FAILED: 'Failed'
      }
      return labels[key] || this.fieldLabel(key.toLowerCase())
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
    },
    actionButtonColor (value) {
      return ['REJECT_OUTBOUND', 'BLOCK'].includes(value) ? 'negative' : 'primary'
    }
  }
}
</script>

<style scoped>
.source-intake-page {
  background: transparent;
}

.source-intake-card {
  width: 100%;
}

.source-intake-workflow {
  background: #f8fafb;
  border-left: 3px solid #1976d2;
  padding: 10px 12px;
}

.source-intake-workflow-history {
  border-top: 1px solid #dfe7eb;
  padding-top: 10px;
}

.source-intake-workflow-event {
  border-bottom: 1px solid #edf1f3;
  padding-bottom: 5px;
}

.source-intake-table {
  width: 100%;
}

.source-intake-time {
  white-space: nowrap;
}

.source-intake-reference-type {
  white-space: nowrap;
}

.source-intake-next {
  max-width: 0;
  white-space: normal;
}

.source-intake-next-label {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-height: 1.25;
  max-height: 2.5em;
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
