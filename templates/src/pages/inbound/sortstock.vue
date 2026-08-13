<template>
    <div>
      <transition appear enter-active-class="animated fadeIn">
      <q-table
        class="my-sticky-header-column-table shadow-24"
        :data="table_list"
        row-key="id"
        :separator="separator"
        :loading="loading"
        :filter="filter"
        :columns="columns"
        hide-bottom
        :pagination.sync="pagination"
        no-data-label="No data"
        no-results-label="No data you want"
        :table-style="{ height: height }"
        flat
        bordered
      >
         <template v-slot:top>
           <q-btn-group push>
             <q-btn :label="$t('refresh')" icon="refresh" @click="reFresh()">
               <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">
                 {{ $t('refreshtip') }}
               </q-tooltip>
             </q-btn>
           </q-btn-group>
           <q-space />
           <q-input outlined rounded dense debounce="300" color="primary" v-model="filter" :placeholder="$t('search')" @input="getSearchList()" @keyup.enter="getSearchList()">
             <template v-slot:append>
               <q-icon name="search" @click="getSearchList()"/>
             </template>
           </q-input>
         </template>
         <template v-slot:body="props">
           <q-tr :props="props">
               <q-td key="asn_code" :props="props">
                 {{ props.row.asn_code }}
               </q-td>
               <q-td key="goods_code" :props="props">
                 {{ props.row.goods_code }}
               </q-td>
               <q-td key="goods_desc" :props="props">
                 {{ props.row.goods_desc }}
               </q-td>
               <q-td key="goods_actual_qty" :props="props">
                 {{ props.row.goods_actual_qty }}
               </q-td>
             <q-td key="sorted_qty" :props="props">
               {{ props.row.sorted_qty }}
             </q-td>
             <q-td key="supplier" :props="props">
               {{ props.row.supplier }}
             </q-td>
             <q-td key="creater" :props="props">
               {{ props.row.creater }}
             </q-td>
             <q-td key="create_time" :props="props">
               {{ props.row.create_time }}
             </q-td>
             <q-td key="update_time" :props="props">
               {{ props.row.update_time }}
             </q-td>
             <q-td key="action" :props="props" style="width: 50px">
               <q-btn round flat push color="teal" icon="qr_code_2" @click="openSerialPanel(props.row)">
                 <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">SN control</q-tooltip>
               </q-btn>
               <q-btn round flat push color="purple" icon="move_to_inbox" @click="MoveToBin(props.row)">
                 <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">
                   {{ $t('putaway') }}
                </q-tooltip>
               </q-btn>
             </q-td>
           </q-tr>
         </template>
      </q-table>
        </transition>
      <template>
        <div v-show="max !== 0" class="q-pa-lg flex flex-center">
           <div>{{ total }} </div>
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
        <div v-show="max === 0" class="q-pa-lg flex flex-center">
          <q-btn flat push color="dark" :label="$t('no_data')"></q-btn>
        </div>
    </template>
      <q-dialog v-model="moveForm">
       <q-card class="shadow-24">
         <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
           <div>{{ movedata.goods_code }}</div>
           <q-space />
           <q-btn dense flat icon="close" v-close-popup>
             <q-tooltip>{{ $t('index.close') }}</q-tooltip>
           </q-btn>
         </q-bar>
         <q-card-section style="max-height: 430px; width: 400px" class="scroll">
           <div v-if="movedata.goods_code" class="q-pa-sm bg-grey-2 text-dark q-mb-sm">
             <div class="text-weight-bold">Putaway readiness</div>
             <div class="text-caption">
               Expected {{ putawayStats(movedata).expected }} ·
               Scanned {{ putawayStats(movedata).scanned }} ·
               Accepted {{ putawayStats(movedata).accepted }} ·
               Hold {{ putawayStats(movedata).held }}
             </div>
             <div class="text-caption text-weight-medium">
               Maximum allowed: {{ putawayMaxQty(movedata) }}
             </div>
             <div v-if="putawayBlockMessage(movedata)" class="text-caption text-negative q-mt-xs">
               {{ putawayBlockMessage(movedata) }}
             </div>
             <div class="q-mt-sm">
               <q-btn
                 v-if="putawayMaxQty(movedata) > 0"
                 flat
                 dense
                 color="primary"
                 :label="'Use ' + putawayMaxQty(movedata) + ' for putaway'"
                 @click="useEligiblePutawayQty()"
               />
               <q-btn
                 v-if="putawayNeedsQcReview(movedata)"
                 flat
                 dense
                 color="negative"
                 label="Review QC"
                 @click="reviewPutawayQc()"
               />
             </div>
           </div>
           <q-select
             v-model="movedata.putaway_driver"
             dense
             outlined
             square
             use-input
             hide-selected
             fill-input
             label="Putaway driver"
             :options="driver_options"
             @focus="loadPutawayDriverOptions()"
             @filter="filterFnDriver"
             style="margin-bottom: 10px"
           >
             <template v-slot:no-option>
               <q-item>
                 <q-item-section class="text-grey">No drivers found</q-item-section>
               </q-item>
             </template>
           </q-select>
           <q-input dense
                    outlined
                    square
                    debounce="500"
                    v-model.number="movedata.qty"
                    type="number"
                    :label="'Putaway Qty (max ' + putawayMaxQty(movedata) + ')'"
                    min="1"
                    :max="putawayMaxQty(movedata)"
                    style="margin-bottom: 5px"
                    :rules="[putawayQuantityRequired, putawayQuantityWithinLimit]"
                    @keyup.enter="MoveToBinSubmit()">
             <template v-slot:before>
               <q-select dense
                         outlined
                         square
                         use-input
                         hide-selected
                         fill-input
                         v-model="movedata.bin_name"
                         :label="$t('warehouse.view_binset.bin_name')"
                         :options="options"
                         @focus="loadBinOptions()"
                         @filter="filterFn"
                         @keyup.enter="MoveToBinSubmit()">
                 <template v-slot:no-option>
                   <q-item>
                     <q-item-section class="text-grey">
                       No results
                     </q-item-section>
                   </q-item>
                 </template>
                 <template v-if="movedata.bin_name" v-slot:append>
                   <q-icon name="cancel" @click.stop="movedata.bin_name = ''" class="cursor-pointer" />
                 </template>
              </q-select>
             </template>
           </q-input>
         </q-card-section>
         <div style="float: right; padding: 15px 15px 15px 0">
           <q-btn color="white" text-color="black" style="margin-right: 25px" @click="MoveToBinCancel()">{{ $t('cancel') }}</q-btn>
           <q-btn color="primary" @click="MoveToBinSubmit()">{{ $t('submit') }}</q-btn>
         </div>
       </q-card>
     </q-dialog>
     <asn-serial-panel
       v-model="serialPanelOpen"
       :asn-code="serialAsnCode"
       :goods-code="serialGoodsCode"
       :asn-context="serialAsnContext"
     />
    </div>
</template>
    <router-view />

<script>
import { getauth, postauth } from 'boot/axios_request'
import { LocalStorage, SessionStorage } from 'quasar'
import AsnSerialPanel from '../../components/AsnSerialPanel.vue'

export default {
  name: 'Pagesorted',
  components: {
    AsnSerialPanel
  },
  data () {
    return {
      openid: '',
      login_name: '',
      authin: '0',
      pathname: 'asn/detail/?asn_status=4',
      pathname_previous: '',
      pathname_next: '',
      separator: 'cell',
      loading: false,
      height: '',
      table_list: [],
      bin_size_list: [],
      bin_property_list: [],
      warehouse_list: [],
      columns: [
        { name: 'asn_code', required: true, label: this.$t('inbound.view_asn.asn_code'), align: 'left', field: 'asn_code' },
        { name: 'goods_code', label: this.$t('goods.view_goodslist.goods_code'), field: 'goods_code', align: 'center' },
        { name: 'goods_desc', label: this.$t('goods.view_goodslist.goods_desc'), field: 'goods_desc', align: 'center' },
        { name: 'goods_actual_qty', label: this.$t('inbound.view_asn.goods_actual_qty'), field: 'goods_actual_qty', align: 'center' },
        { name: 'sorted_qty', label: this.$t('inbound.view_asn.sorted_qty'), field: 'sorted_qty', align: 'center' },
        { name: 'supplier', label: this.$t('baseinfo.view_supplier.supplier_name'), field: 'supplier', align: 'center' },
        { name: 'creater', label: this.$t('creater'), field: 'creater', align: 'center' },
        { name: 'create_time', label: this.$t('createtime'), field: 'create_time', align: 'center' },
        { name: 'update_time', label: this.$t('updatetime'), field: 'update_time', align: 'center' },
        { name: 'action', label: this.$t('action'), align: 'right' }
      ],
      filter: '',
      asnFilter: '',
      pagination: {
        page: 1,
        rowsPerPage: '30'
      },
      options: [],
      driver_options: LocalStorage.getItem('putaway_driver_name_list') || [],
      moveForm: false,
      movedata: {},
      error1: this.$t('inbound.view_sortstock.error1'),
      current: 1,
      max: 0,
      total: 0,
      paginationIpt: 1,
      serialPanelOpen: false,
      serialAsnCode: '',
      serialGoodsCode: '',
      serialAsnContext: {}
    }
  },
  methods: {
    openSerialPanel (e) {
      this.serialAsnCode = e.asn_code
      this.serialGoodsCode = e.goods_code
      this.serialAsnContext = e || {}
      this.serialPanelOpen = true
    },
    getList () {
      var _this = this
      if (_this.$q.localStorage.has('auth')) {
        const asnFilter = _this.asnFilter ? '&asn_code__icontains=' + encodeURIComponent(_this.asnFilter) : ''
        getauth(_this.pathname + asnFilter + '&page=' + '' + _this.current, {
        }).then(res => {
          _this.table_list = res.results
          _this.total = res.count
          if (res.count === 0) {
            _this.max = 0
          } else {
            if (Math.ceil(res.count / 30) === 1) {
              _this.max = 0
            } else {
              _this.max = Math.ceil(res.count / 30)
            }
          }
          _this.pathname_previous = res.previous
          _this.pathname_next = res.next
        }).catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
      }
    },
    changePageEnter (e) {
      if (Number(this.paginationIpt) < 1) {
        this.current = 1
        this.paginationIpt = 1
      } else if (Number(this.paginationIpt) > this.max) {
        this.current = this.max
        this.paginationIpt = this.max
      } else {
        this.current = Number(this.paginationIpt)
      }
      this.getList()
    },
    getSearchList () {
      var _this = this
      if (_this.$q.localStorage.has('auth')) {
        _this.current = 1
        _this.paginationIpt = 1
        const search = _this.filter || _this.asnFilter
        getauth(_this.pathname + '&asn_code__icontains=' + encodeURIComponent(search) + '&page=' + '' + _this.current, {
        }).then(res => {
          _this.table_list = res.results
          _this.total = res.count
          if (res.count === 0) {
            _this.max = 0
          } else {
            if (Math.ceil(res.count / 30) === 1) {
              _this.max = 0
            } else {
              _this.max = Math.ceil(res.count / 30)
            }
          }
          _this.pathname_previous = res.previous
          _this.pathname_next = res.next
        }).catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
      } else {
      }
    },
    getListPrevious () {
      var _this = this
      if (_this.$q.localStorage.has('auth')) {
        getauth(_this.pathname_previous, {
        }).then(res => {
          _this.table_list = res.results
          _this.pathname_previous = res.previous
          _this.pathname_next = res.next
        }).catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
      } else {
      }
    },
    getListNext () {
      var _this = this
      if (_this.$q.localStorage.has('auth')) {
        getauth(_this.pathname_next, {
        }).then(res => {
          _this.table_list = res.results
          _this.pathname_previous = res.previous
          _this.pathname_next = res.next
        }).catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
      } else {
      }
    },
    reFresh () {
      var _this = this
      _this.getList()
    },
    MoveToBin (e) {
      var _this = this
      _this.moveForm = true
      _this.movedata = { ...e, putaway_driver: '', qty: 0, putaway_context: e }
      _this.movedata.qty = _this.putawayMaxQty(_this.movedata)
      _this.loadPutawayDriverOptions()
      _this.loadBinOptions()
      getauth('asn/list/?asn_code=' + encodeURIComponent(e.asn_code)).then(res => {
        const row = (res.results || [])[0]
        if (row) {
          _this.movedata.putaway_context = { ...e, ...row }
          _this.movedata.serial_acceptance = row.serial_acceptance
          _this.movedata.actual_qty = row.actual_qty
          _this.movedata.putaway_qty = row.putaway_qty
          if (row.putaway_driver) _this.movedata.putaway_driver = row.putaway_driver
          _this.movedata.qty = _this.putawayMaxQty(_this.movedata)
        }
      }).catch(() => {})
    },
    MoveToBinSubmit () {
      var _this = this
      if (!_this.movedata.putaway_driver) {
        _this.$q.notify({
          message: 'Please assign a putaway driver',
          icon: 'close',
          color: 'negative'
        })
      } else if (!_this.movedata.bin_name) {
        _this.$q.notify({
          message: 'Please Enter the Bin Name',
          icon: 'close',
          color: 'negative'
        })
      } else if (Number(_this.movedata.qty) <= 0) {
        _this.$q.notify({
          message: 'Enter a putaway quantity',
          icon: 'close',
          color: 'negative'
        })
      } else if (Number(_this.movedata.qty) > _this.putawayMaxQty(_this.movedata)) {
        _this.$q.notify({
          message: _this.putawayQuantityError(_this.movedata.qty),
          icon: 'close',
          color: 'negative'
        })
      } else {
        const payload = { ..._this.movedata }
        delete payload.putaway_context
        postauth('asn/movetobin/' + _this.movedata.id + '/', payload).then(res => {
          _this.getList()
          _this.MoveToBinCancel()
          _this.$q.notify({
            message: res.detail || 'Putaway completed',
            icon: 'check',
            color: 'green'
          })
        }).catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
      }
    },
    MoveToBinCancel () {
      var _this = this
      _this.moveForm = false
      _this.movedata = {}
    },
    putawayContext (row) {
      return (row && row.putaway_context) || row || {}
    },
    putawayStats (row) {
      const context = this.putawayContext(row)
      const summary = context.serial_acceptance || {}
      const hasSerialResult = Boolean(summary.status && summary.status !== 'NOT_IMPORTED')
      const actual = Number(context.goods_actual_qty || context.actual_qty || 0)
      const alreadyPutaway = Number(context.sorted_qty || context.putaway_qty || 0)
      const remaining = Math.max(actual - alreadyPutaway, 0)
      const expected = hasSerialResult ? Number(summary.expected || actual) : actual
      const scanned = hasSerialResult ? Number(summary.scan_record_count || summary.received || 0) : 0
      const accepted = hasSerialResult
        ? Number(summary.eligible_for_putaway || summary.accepted_for_putaway || summary.accepted || 0)
        : remaining
      const held = hasSerialResult ? Number(summary.held || 0) : 0
      const repair = hasSerialResult ? Number(summary.repair || 0) : 0
      const rejected = hasSerialResult ? Number(summary.rejected || 0) : 0
      const openExceptions = hasSerialResult ? Number(summary.open_exception_count || 0) : 0
      const maximum = hasSerialResult
        ? Math.max(0, Math.min(remaining, accepted - alreadyPutaway))
        : remaining
      return {
        hasSerialResult,
        actual,
        alreadyPutaway,
        remaining,
        expected,
        scanned,
        accepted,
        held,
        repair,
        rejected,
        openExceptions,
        maximum
      }
    },
    putawayMaxQty (row) {
      return this.putawayStats(row).maximum
    },
    putawayNeedsQcReview (row) {
      const stats = this.putawayStats(row)
      return stats.hasSerialResult && (
        stats.held > 0 || stats.repair > 0 || stats.rejected > 0 || stats.openExceptions > 0
      )
    },
    putawayBlockMessage (row) {
      const stats = this.putawayStats(row)
      if (!stats.hasSerialResult) {
        return 'SN result not imported. Putaway is limited by received quantity.'
      }
      if (stats.maximum < stats.remaining) {
        const blocked = Math.max(stats.remaining - stats.maximum, 0)
        return `${blocked} unit(s) are not eligible for putaway. Review QC before moving them.`
      }
      return ''
    },
    putawayQuantityRequired (value) {
      return Number(value) > 0 || 'Enter a putaway quantity'
    },
    putawayQuantityError (value) {
      return `Quantity exceeds the eligible quantity. Maximum allowed is ${this.putawayMaxQty(this.movedata)}.`
    },
    putawayQuantityWithinLimit (value) {
      return Number(value) <= this.putawayMaxQty(this.movedata) || this.putawayQuantityError(value)
    },
    useEligiblePutawayQty () {
      this.movedata.qty = this.putawayMaxQty(this.movedata)
    },
    reviewPutawayQc () {
      const row = this.putawayContext(this.movedata)
      this.moveForm = false
      this.openSerialPanel(row)
    },
    loadBinOptions (needle = '') {
      var _this = this
      const query = encodeURIComponent(String(needle || '').trim().toLowerCase())
      getauth('binset/?bin_name__icontains=' + query).then(res => {
        const rows = Array.isArray(res) ? res : (res.results || [])
        const binlist = rows
          .filter(detail => {
            const name = String(detail.bin_name || '').toUpperCase()
            const role = String(detail.location_role || '').toUpperCase()
            return role !== 'STAGING' && !name.startsWith('STAGE-')
          })
          .map(detail => detail.bin_name)
          .filter(Boolean)
        SessionStorage.set('bin_name', binlist)
        _this.options = binlist
      }).catch(err => {
        _this.$q.notify({
          message: err.detail,
          icon: 'close',
          color: 'negative'
        })
      })
    },
    filterFn (val, update) {
      update(() => {
        this.loadBinOptions(val)
      })
    },
    loadPutawayDriverOptions (needle = '') {
      getauth('driver/?driver_name__icontains=' + encodeURIComponent(needle)).then(res => {
        const rows = Array.isArray(res) ? res : (res.results || [])
        const options = rows.map(item => item.driver_name).filter(Boolean)
        this.driver_options = options
        LocalStorage.set('putaway_driver_name_list', options)
      }).catch(() => {})
    },
    filterFnDriver (val, update) {
      update(() => {
        this.loadPutawayDriverOptions(val)
      })
    }
  },
  created () {
    var _this = this
    _this.asnFilter = (_this.$route.query && _this.$route.query.asn_code) || ''
    if (_this.$q.localStorage.has('openid')) {
      _this.openid = _this.$q.localStorage.getItem('openid')
    } else {
      _this.openid = ''
      _this.$q.localStorage.set('openid', '')
    }
    if (_this.$q.localStorage.has('login_name')) {
      _this.login_name = _this.$q.localStorage.getItem('login_name')
    } else {
      _this.login_name = ''
      _this.$q.localStorage.set('login_name', '')
    }
    if (_this.$q.localStorage.has('auth')) {
      _this.authin = '1'
      _this.getList()
    } else {
      _this.authin = '0'
    }
  },
  mounted () {
    var _this = this
    if (_this.$q.platform.is.electron) {
      _this.height = String(_this.$q.screen.height - 290) + 'px'
    } else {
      _this.height = _this.$q.screen.height - 290 + '' + 'px'
    }
  },
  updated () {
  },
  destroyed () {
  }
}
</script>
