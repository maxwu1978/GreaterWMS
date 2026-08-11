<template>
  <div>
    <transition appear enter-active-class="animated fadeIn">
      <q-table
        class="my-sticky-header-column-table shadow-24"
        :data="table_list"
        row-key="id"
        :separator="separator"
        :loading="loading"
        :columns="columns"
        hide-bottom
        :pagination.sync="pagination"
        dense
        no-data-label="No data"
        no-results-label="No data you want"
        :table-style="{ height: height }"
        flat
        bordered
      >
        <template v-slot:top>
          <q-btn
            :label="$t('refresh')"
            icon="refresh"
            :disable="loading"
            @click="reFresh()"
          />
          <q-space />
          <q-input
            outlined
            rounded
            dense
            debounce="300"
            color="primary"
            v-model="filter"
            :placeholder="$t('search')"
            @input="getSearchList()"
            @keyup.enter="getSearchList()"
          >
            <template v-slot:append>
              <q-icon name="search" @click="getSearchList()" />
            </template>
          </q-input>
        </template>

        <template v-slot:body="props">
          <q-tr :props="props">
            <q-td key="asn_code" :props="props">{{ props.row.asn_code }}</q-td>
            <q-td key="asn_status" :props="props">
              <q-chip dense square color="blue-2" text-color="dark">
                {{ statusLabel(props.row.asn_status) }}
              </q-chip>
            </q-td>
            <q-td key="sku_count" :props="props" class="text-center">
              {{ props.row.sku_count || 0 }}
            </q-td>
            <q-td key="planned_qty" :props="props" class="text-center">
              {{ props.row.planned_qty || 0 }}
            </q-td>
            <q-td key="actual_qty" :props="props" class="text-center">
              {{ props.row.actual_qty || 0 }}
            </q-td>
            <q-td key="staging_bin" :props="props">
              <span class="text-grey-6">{{ props.row.staging_bin || '-' }}</span>
            </q-td>
            <q-td key="pack_list_status" :props="props">
              <q-chip
                dense
                square
                :color="packListColor(props.row.pack_list_status)"
                text-color="dark"
              >
                {{ packListLabel(props.row.pack_list_status) }}
                <q-icon
                  v-if="props.row.pack_list_has_serials"
                  name="qr_code_2"
                  size="14px"
                  class="q-ml-xs"
                >
                  <q-tooltip>{{ $t('asn_actions.serial_numbers') }}</q-tooltip>
                </q-icon>
              </q-chip>
            </q-td>
            <q-td key="exception_qty" :props="props" class="text-center">
              <q-chip
                v-if="Number(props.row.exception_qty || 0) > 0"
                dense
                square
                color="negative"
                text-color="white"
              >
                {{ props.row.exception_qty }}
              </q-chip>
              <span v-else class="text-grey-6">0</span>
            </q-td>
            <q-td key="next_action" :props="props">
              <q-btn
                dense
                unelevated
                no-caps
                color="primary"
                icon="local_shipping"
                :label="$t('inbound.view_asn.confirm_arrival')"
                @click="openPreload(props.row)"
              />
            </q-td>
            <q-td key="action" :props="props" style="width: 56px">
              <q-btn-dropdown flat dense round icon="more_vert" color="grey-8">
                <q-list dense>
                  <q-item clickable v-close-popup @click="openAsn()">
                    <q-item-section avatar><q-icon name="visibility" /></q-item-section>
                    <q-item-section>{{ $t('asn_actions.view') }}</q-item-section>
                  </q-item>
                  <q-item clickable v-close-popup @click="openPackList(props.row)">
                    <q-item-section avatar><q-icon name="description" /></q-item-section>
                    <q-item-section>{{ $t('asn_actions.pack_list') }}</q-item-section>
                  </q-item>
                  <q-item clickable v-close-popup @click="openSerialPanel(props.row)">
                    <q-item-section avatar><q-icon name="qr_code_2" /></q-item-section>
                    <q-item-section>{{ $t('asn_actions.serial_numbers') }}</q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
            </q-td>
          </q-tr>
        </template>
      </q-table>
    </transition>

    <div v-show="max !== 0" class="q-pa-lg flex flex-center">
      <div>{{ total }}</div>
      <q-pagination
        v-model="current"
        color="black"
        :max="max"
        :max-pages="6"
        boundary-links
        @click="getList()"
      />
      <div>
        <input
          v-model="paginationIpt"
          @blur="changePageEnter"
          @keyup.enter="changePageEnter"
          style="width: 60px; text-align: center"
        />
      </div>
    </div>
    <div v-show="max === 0 && total === 0" class="q-pa-lg flex flex-center">
      <q-btn flat push color="dark" :label="$t('no_data')" />
    </div>

    <q-dialog v-model="preloadForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ preloadAsnCode }} - {{ $t('inbound.view_asn.confirm_arrival') }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup />
        </q-bar>
        <q-card-section style="max-height: 500px; width: 500px" class="scroll">
          <div class="text-subtitle2 q-mb-sm">
            {{ $t('inbound.view_asn.confirm_arrival') }}: choose staging location
          </div>
          <StagingSlotPicker
            flow="INBOUND"
            v-model="preloadStagingBin"
            :multiple="true"
            :max-selections="preloadRequiredSlots"
          />
          <div class="text-caption text-grey-7 q-mt-sm">
            Required standard staging locations: {{ preloadRequiredSlots }}
          </div>
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn
            color="white"
            text-color="black"
            style="margin-right: 25px"
            @click="preloadDataCancel()"
          >
            {{ $t('cancel') }}
          </q-btn>
          <q-btn
            color="primary"
            :disable="loading || !preloadRequiredSlots"
            @click="preloadDataSubmit()"
          >
            {{ $t('submit') }}
          </q-btn>
        </div>
      </q-card>
    </q-dialog>

    <asn-serial-panel v-model="serialPanelOpen" :asn-code="serialAsnCode" />
  </div>
</template>
<router-view />

<script>
import { getauth, postauth } from 'boot/axios_request'
import AsnSerialPanel from '../../components/AsnSerialPanel.vue'
import StagingSlotPicker from '../../components/StagingSlotPicker.vue'

export default {
  name: 'Pageasnprearrival',
  components: {
    AsnSerialPanel,
    StagingSlotPicker
  },
  data () {
    return {
      pathname: 'asn/',
      pathname_previous: '',
      pathname_next: '',
      separator: 'cell',
      loading: false,
      height: '',
      table_list: [],
      columns: [
        { name: 'asn_code', required: true, label: this.$t('inbound.view_asn.asn_code'), align: 'left', field: 'asn_code' },
        { name: 'asn_status', label: this.$t('inbound.view_asn.asn_status'), field: 'asn_status', align: 'center' },
        { name: 'sku_count', label: this.$t('inbound.view_asn.sku_count'), field: 'sku_count', align: 'center' },
        { name: 'planned_qty', label: this.$t('inbound.view_asn.planned_qty'), field: 'planned_qty', align: 'center' },
        { name: 'actual_qty', label: this.$t('inbound.view_asn.actual_qty'), field: 'actual_qty', align: 'center' },
        { name: 'staging_bin', label: this.$t('inbound.view_asn.staging_bin'), field: 'staging_bin', align: 'left' },
        { name: 'pack_list_status', label: this.$t('inbound.view_asn.pack_list_status'), field: 'pack_list_status', align: 'center' },
        { name: 'exception_qty', label: this.$t('inbound.view_asn.exception_qty'), field: 'exception_qty', align: 'center' },
        { name: 'next_action', label: this.$t('inbound.view_asn.next_action'), align: 'left' },
        { name: 'action', label: this.$t('action'), align: 'right' }
      ],
      filter: '',
      pagination: {
        page: 1,
        rowsPerPage: '30'
      },
      current: 1,
      max: 0,
      total: 0,
      paginationIpt: 1,
      preloadForm: false,
      preloadid: 0,
      preloadAsnCode: '',
      preloadStagingBin: [],
      preloadRequiredSlots: 0,
      serialPanelOpen: false,
      serialAsnCode: ''
    }
  },
  methods: {
    statusLabel (status) {
      return Number(status) === 1 ? this.$t('inbound.predeliverystock') : 'N/A'
    },
    packListLabel (status) {
      const labels = {
        NOT_RECEIVED: this.$t('inbound.view_asn.pack_list_not_received'),
        PENDING: this.$t('inbound.view_asn.pack_list_pending'),
        CONFIRMED: this.$t('inbound.view_asn.pack_list_confirmed')
      }
      return labels[status] || labels.NOT_RECEIVED
    },
    packListColor (status) {
      return {
        NOT_RECEIVED: 'grey-4',
        PENDING: 'orange-3',
        CONFIRMED: 'green-3'
      }[status] || 'grey-4'
    },
    formatRows (rows) {
      return (rows || []).map(item => Object.assign({}, item, {
        asn_status: Number(item.asn_status)
      }))
    },
    applyResponse (res) {
      this.table_list = this.formatRows(res.results)
      this.total = res.count || 0
      this.max = this.total > 30 ? Math.ceil(this.total / 30) : 0
      this.pathname_previous = res.previous
      this.pathname_next = res.next
    },
    getList () {
      if (!this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth(this.pathname + 'list/?asn_status=1&page=' + this.current, {})
        .then(res => this.applyResponse(res))
        .catch(err => {
          this.$q.notify({
            message: err.detail || 'Unable to load pre-delivery ASNs',
            icon: 'close',
            color: 'negative'
          })
        })
        .finally(() => {
          this.loading = false
        })
    },
    getSearchList () {
      if (!this.$q.localStorage.has('auth')) return
      this.current = 1
      this.paginationIpt = 1
      this.loading = true
      getauth(
        this.pathname + 'list/?asn_status=1&asn_code__icontains=' + encodeURIComponent(this.filter) + '&page=1',
        {}
      )
        .then(res => this.applyResponse(res))
        .catch(err => {
          this.$q.notify({
            message: err.detail || 'Unable to search pre-delivery ASNs',
            icon: 'close',
            color: 'negative'
          })
        })
        .finally(() => {
          this.loading = false
        })
    },
    getListPrevious () {
      if (!this.pathname_previous || !this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth(this.pathname_previous, {})
        .then(res => this.applyResponse(res))
        .finally(() => {
          this.loading = false
        })
    },
    getListNext () {
      if (!this.pathname_next || !this.$q.localStorage.has('auth')) return
      this.loading = true
      getauth(this.pathname_next, {})
        .then(res => this.applyResponse(res))
        .finally(() => {
          this.loading = false
        })
    },
    changePageEnter () {
      if (Number(this.paginationIpt) < 1) {
        this.current = 1
      } else if (Number(this.paginationIpt) > this.max) {
        this.current = this.max || 1
      } else {
        this.current = Number(this.paginationIpt)
      }
      this.paginationIpt = this.current
      this.getList()
    },
    reFresh () {
      this.getList()
    },
    openAsn () {
      this.$router.push({ name: 'asn' })
    },
    openPackList (row) {
      this.$router.push({ name: 'packlist', query: { asn_code: row.asn_code } })
    },
    openSerialPanel (row) {
      this.serialAsnCode = row.asn_code
      this.serialPanelOpen = true
    },
    openPreload (row) {
      if (Number(row.asn_status) !== 1) return
      this.preloadForm = true
      this.preloadid = row.id
      this.preloadAsnCode = row.asn_code
      this.preloadStagingBin = []
      this.preloadRequiredSlots = Number(row.planned_qty || 0)
      getauth(this.pathname + 'detail/?asn_code=' + encodeURIComponent(row.asn_code), {})
        .then(res => {
          this.preloadRequiredSlots = (res.results || []).reduce((total, item) => {
            return total + Number(item.goods_qty || 0)
          }, 0)
        })
        .catch(err => {
          this.preloadDataCancel()
          this.$q.notify({
            message: err.detail || 'Unable to load ASN details',
            icon: 'close',
            color: 'negative'
          })
        })
    },
    preloadDataSubmit () {
      if (!this.preloadRequiredSlots || this.preloadStagingBin.length !== this.preloadRequiredSlots) {
        this.$q.notify({
          message: 'Please select exactly ' + this.preloadRequiredSlots + ' staging locations',
          icon: 'close',
          color: 'negative'
        })
        return
      }
      this.loading = true
      postauth('asn/preload/' + this.preloadid + '/', {
        staging_bins: this.preloadStagingBin
      })
        .then(() => {
          this.preloadDataCancel()
          this.getList()
          this.$q.notify({
            message: 'Success Confirm ASN Delivery',
            icon: 'check',
            color: 'green'
          })
        })
        .catch(err => {
          this.$q.notify({
            message: err.detail || 'Unable to confirm ASN delivery',
            icon: 'close',
            color: 'negative'
          })
        })
        .finally(() => {
          this.loading = false
        })
    },
    preloadDataCancel () {
      this.preloadForm = false
      this.preloadid = 0
      this.preloadAsnCode = ''
      this.preloadStagingBin = []
      this.preloadRequiredSlots = 0
    }
  },
  created () {
    if (this.$q.localStorage.has('auth')) {
      this.getList()
    }
  },
  mounted () {
    if (this.$q.platform.is.electron) {
      this.height = String(this.$q.screen.height - 290) + 'px'
    } else {
      this.height = this.$q.screen.height - 290 + 'px'
    }
  }
}
</script>
