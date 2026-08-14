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
            <q-btn
              :label="$t('new')"
              icon="add"
              @click="newFormOpen()"
            >
              <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('newtip') }}</q-tooltip>
            </q-btn>
            <q-btn :label="$t('refresh')" icon="refresh" @click="reFresh()">
              <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('refreshtip') }}</q-tooltip>
            </q-btn>
            <q-btn
              :label="$t('release')"
              icon="img:statics/outbound/orderrelease.png"
              @click="orderreleaseAllData()"
            >
              <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('releaseallorder') }}</q-tooltip>
            </q-btn>
          </q-btn-group>
          <q-space />
          <q-input outlined rounded dense debounce="300" color="primary" v-model="filter" :placeholder="$t('search')" @input="getSearchList()" @keyup.enter="getSearchList()">
            <template v-slot:append>
              <q-icon name="search" @click="getSearchList()" />
            </template>
          </q-input>
        </template>
        <template v-slot:body="props">
          <q-tr :props="props">
            <q-td key="dn_code" :props="props" class="outbound-nowrap">{{ props.row.dn_code }}</q-td>
            <q-td key="dn_status" :props="props">
              <q-badge :color="props.row.dn_status_code === 7 ? 'negative' : 'primary'" outline>{{ props.row.dn_status }}</q-badge>
            </q-td>
            <q-td key="customer" :props="props" class="outbound-nowrap">{{ props.row.customer || '-' }}</q-td>
            <q-td key="sku_summary" :props="props" class="outbound-nowrap">{{ props.row.sku_summary || '-' }}</q-td>
            <q-td key="dispatch_driver" :props="props" class="outbound-nowrap">{{ props.row.dispatch_driver || '-' }}</q-td>
            <q-td key="staging_bin" :props="props" class="outbound-nowrap">
              <div>{{ props.row.staging_bin || '-' }}</div>
              <div class="text-caption text-grey-6">{{ props.row.staging_status || 'Not assigned' }}</div>
            </q-td>
            <q-td key="delivery_exception" :props="props" class="outbound-nowrap">
              <q-badge v-if="props.row.delivery_exception" color="negative">
                {{ props.row.delivery_exception }}
                <q-tooltip v-if="props.row.cancellation_note">{{ props.row.cancellation_note }}</q-tooltip>
              </q-badge>
              <span v-else class="text-grey-6">-</span>
            </q-td>
            <q-td key="next_step" :props="props" class="outbound-nowrap">{{ props.row.next_step }}</q-td>
            <q-td key="update_time" :props="props" class="outbound-nowrap">{{ props.row.update_time }}</q-td>
            <q-td key="action" :props="props" class="outbound-action-cell">
              <q-btn
                round
                flat
                push
                color="info"
                icon="visibility"
                @click="viewData(props.row)"
              >
                <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">{{ $t('printthisdn') }}</q-tooltip>
              </q-btn>
              <q-btn-dropdown round flat dense color="primary" dropdown-icon="more_vert">
                <q-list dense>
                  <q-item v-if="canAction(props.row, 'confirm')" clickable v-close-popup @click="neworderData(props.row)">
                    <q-item-section>{{ $t('confirmorder') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'release')" clickable v-close-popup @click="orderreleaseData(props.row)">
                    <q-item-section>{{ $t('releaseorder') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'print')" clickable v-close-popup @click="PrintPickingList(props.row)">
                    <q-item-section>{{ $t('print') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'pick')" clickable v-close-popup @click="pickedData(props.row)">
                    <q-item-section>{{ $t('confirmpicked') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'dispatch')" clickable v-close-popup @click="DispatchDN(props.row)">
                    <q-item-section>{{ $t('dispatch') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'pod')" clickable v-close-popup @click="PODData(props.row)">
                    <q-item-section>{{ $t('outbound.pod') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'cancel_intransit')" clickable v-close-popup @click="cancelInTransitData(props.row)">
                    <q-item-section>Cancel In Transit</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'edit')" clickable v-close-popup @click="editData(props.row)">
                    <q-item-section>{{ $t('edit') }}</q-item-section>
                  </q-item>
                  <q-item v-if="canAction(props.row, 'delete')" clickable v-close-popup @click="deleteData(props.row)">
                    <q-item-section>{{ $t('delete') }}</q-item-section>
                  </q-item>
                </q-list>
              </q-btn-dropdown>
            </q-td>
            <template v-if="props.row.transportation_fee.detail !== []">
              <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]" content-style="font-size: 12px">
                <q-list>
                  <div v-for="(transportation_fee, index) in props.row.transportation_fee.detail" :key="index">
                    <q-item v-ripple>
                      <q-item-section>
                        <q-item-label>{{ transportation_fee.transportation_supplier }}</q-item-label>
                        <q-item-label>{{ $t('estimate') }}: {{ transportation_fee.transportation_cost }}</q-item-label>
                      </q-item-section>
                    </q-item>
                  </div>
                </q-list>
              </q-tooltip>
            </template>
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
    <q-dialog v-model="newForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ newFormData.dn_code }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">
          <q-select
            filled
            use-input
            fill-input
            hide-selected
            input-debounce="0"
            dense
            outlined
            square
            v-model="newFormData.customer"
            :options="customer_list"
            @filter="filterFnS"
            @input-value="setModel"
            :label="$t('baseinfo.view_customer.customer_name')"
            style="margin-bottom: 5px"
            :rules="[val => (val && val.length > 0) || error1]"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:Sno-option>
              <q-item>
                <q-item-section class="text-grey">
                  No Result
                </q-item-section>
              </q-item>
            </template>
          </q-select>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData1.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData1.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(1)"
                @input-value="setOptions"
                @filter="filterFn"
                autofocus
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData1.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData1.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData2.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData2.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(2)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData2.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData2.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData3.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData3.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(3)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData3.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData3.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData4.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData4.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(4)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData4.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData4.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData5.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData5.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(5)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData5.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData5.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData6.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData6.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(6)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData6.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData6.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData7.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData7.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(7)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData7.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData7.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData8.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData8.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(8)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData8.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData8.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData9.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData9.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(9)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData9.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData9.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
          <q-input
            dense
            outlined
            square
            debounce="500"
            v-model.number="goodsData10.qty"
            type="number"
            :label="$t('stock.view_stocklist.goods_qty')"
            style="margin-bottom: 5px"
            @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
          >
            <template v-slot:before>
              <q-select
                dense
                outlined
                square
                use-input
                hide-selected
                fill-input
                v-model="goodsData10.code"
                :label="$t('goods.view_goodslist.goods_code')"
                :options="options"
                @focus="getFocus(10)"
                @input-value="setOptions"
                @filter="filterFn"
                @keyup.enter="isEdit ? editDataSubmit() : newDataSubmit()"
              >
                <template v-slot:no-option>
                  <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
                </template>
                <template v-if="goodsData10.code" v-slot:append>
                  <q-icon name="cancel" @click.stop="goodsData10.code = ''" class="cursor-pointer" />
                </template>
              </q-select>
            </template>
          </q-input>
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="isEdit ? editDataCancel() : newDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="isEdit ? editDataSubmit() : newDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="deleteForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('delete') }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">{{ $t('deletetip') }}</q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="deleteDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="deleteDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="neworderForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('confirmorder') }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">{{ $t('deletetip') }}</q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="neworderDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="neworderDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="orderreleaseForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('releaseorder') }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">{{ $t('deletetip') }}</q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="orderreleaseDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="orderreleaseDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="viewForm">
      <q-card id="printMe">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ viewdn }}</div>
          <q-space />
          {{ $t('outbound.dn') }}
        </q-bar>
        <q-card-section>
          <div class="row">
            <div class="col-8">
              <div class="text-h6">Sender: {{ warehouse_detail.warehouse_name }}</div>
              <div class="text-subtitle2">Address: {{ warehouse_detail.warehouse_city }}{{ warehouse_detail.warehouse_address }}</div>
              <div class="text-subtitle2">Tel: {{ warehouse_detail.warehouse_contact }}</div>
              <div class="text-h6">Receiver: {{ customer_detail.customer_name }}</div>
              <div class="text-subtitle2">Address: {{ customer_detail.customer_city }}{{ customer_detail.customer_address }}</div>
              <div class="text-subtitle2">Tel: {{ customer_detail.customer_contact }}</div>
            </div>
            <div class="col-4"><img :src="bar_code" style="width: 70%; margin-left: 15%" /></div>
          </div>
        </q-card-section>
        <q-markup-table>
          <thead>
            <tr>
              <th class="text-left">{{ $t('goods.view_goodslist.goods_code') }}</th>
              <th class="text-right">{{ $t('outbound.view_dn.total_weight') }}</th>
              <th class="text-right">{{ $t('outbound.view_dn.total_volume') }}</th>
              <th class="text-right">{{ $t('outbound.view_dn.intransit_qty') }}</th>
              <th class="text-right">Comments</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(view, index) in viewprint_table" :key="index">
              <td class="text-left">{{ view.goods_code }}</td>
              <td class="text-right">{{ view.goods_weight }}</td>
              <td class="text-right">{{ view.goods_volume }}</td>
              <td class="text-right">{{ view.picked_qty }}</td>
              <td class="text-right"></td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card>
      <div style="float: right; padding: 15px 15px 15px 0"><q-btn color="primary" icon="print" v-print="printObj">print</q-btn></div>
    </q-dialog>
    <q-dialog v-model="viewPLForm">
      <q-card id="printPL">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('print') }}</div>
          <q-space />
        </q-bar>
        <div class="col-4" style="margin-top: 5%;"><img :src="bar_code" style="width: 21%;margin-left: 70%" /></div>
        <q-markup-table>
          <thead>
            <tr>
              <th class="text-left">{{ $t('outbound.view_dn.dn_code') }}</th>
              <th class="text-right">{{ $t('warehouse.view_binset.bin_name') }}</th>
              <th class="text-right">{{ $t('goods.view_goodslist.goods_code') }}</th>
              <th class="text-right">{{ $t('outbound.pickstock') }}</th>
              <th class="text-right">{{ $t('outbound.pickedstock') }}</th>
              <th class="text-right">Comments</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(view, index) in pickinglist_print_table" :key="index">
              <td class="text-left">{{ view.dn_code }}</td>
              <td class="text-right">{{ view.bin_name }}</td>
              <td class="text-right">{{ view.goods_code }}</td>
              <td class="text-right">{{ view.pick_qty }}</td>
              <td class="text-right" v-show="picklist_check === 0"></td>
              <td class="text-right" v-show="picklist_check > 0">{{ view.picked_qty }}</td>
              <td class="text-right"></td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card>
      <div style="float: right; padding: 15px 15px 15px 0"><q-btn color="primary" icon="print" v-print="printPL">print</q-btn></div>
    </q-dialog>
    <q-dialog v-model="pickedForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ pickFormData.dn_code }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">
          <q-input
            dense
            outlined
            square
            debounce="500"
            disable
            readonly
            v-model="pickFormData.customer"
            :label="$t('baseinfo.view_customer.customer_name')"
            style="margin-bottom: 5px"
          />
          <div v-for="(item, index) in pickFormData.goodsData" :key="index">
            <q-input dense outlined square bottom-slots type="number" v-model="item.pick_qty" :label="item.goods_code">
              <template v-slot:append>
                {{ item.bin_name }}
              </template>
            </q-input>
          </div>
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="pickedDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="pickedDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="dispatchForm">
      <q-card class="shadow-24">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ dispatchFormData.dn_code }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">
          <q-select
            dense
            outlined
            square
            use-input
            hide-selected
            fill-input
            v-model="dispatchFormData.driver"
            :label="$t('driver.view_driver.driver_name')"
            :options="driver_options"
            @filter="filterFnDispatch"
            autofocus
            @keyup.enter="dispatchDataSubmit()"
          >
            <template v-slot:no-option>
              <q-item><q-item-section class="text-grey">No results</q-item-section></q-item>
            </template>
            <template v-if="dispatchFormData.driver" v-slot:append>
              <q-icon name="cancel" @click.stop="dispatchFormData.driver = ''" class="cursor-pointer" />
            </template>
          </q-select>
          <StagingSlotPicker
            flow="OUTBOUND"
            v-model="dispatchFormData.staging_bin"
            class="q-mt-md"
          />
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="dispatchDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="dispatchDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="podForm">
      <q-card class="shadow-24 outbound-pod-card">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>{{ $t('outbound.dn') }}: {{ podFormData.dn_code }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">
          {{ $t('baseinfo.customer') }}: {{ podFormData.customer }}
          <div v-for="(item, index) in podFormData.goodsData" :key="index">
            <div class="text-caption text-grey-7 q-mt-sm">{{ item.goods_code }} · Expected: {{ item.expected_delivery_qty }}</div>
            <q-input
              dense
              outlined
              square
              debounce="500"
              v-model.number="item.intransit_qty"
              type="number"
              :label="$t('outbound.view_dn.delivery_actual_qty')"
              style="margin-bottom: 5px"
              :error-message="error2"
              :error="isError1"
              :rules="[validate1]"
            >
              <template v-slot:after>
                <q-input
                  dense
                  outlined
                  square
                  debounce="500"
                  v-model.number="item.delivery_damage_qty"
                  type="number"
                  :label="$t('outbound.view_dn.delivery_damage_qty')"
                  style="margin-top: 11%"
                  :error-message="error2"
                  :error="isError2"
                  :rules="[validate2(item.delivery_damage_qty, item.intransit_qty)]"
                ></q-input>
              </template>
            </q-input>
            <q-input
              dense
              outlined
              square
              v-model="item.delivery_note"
              label="Exception note"
              hint="Required when shortage, more quantity, or damage is recorded"
              class="q-mt-xs"
            />
          </div>
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="PODDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="primary" @click="PODDataSubmit()">{{ $t('submit') }}</q-btn>
        </div>
      </q-card>
    </q-dialog>
    <q-dialog v-model="cancelInTransitForm">
      <q-card class="shadow-24 outbound-pod-card">
        <q-bar class="bg-light-blue-10 text-white rounded-borders" style="height: 50px">
          <div>Cancel In Transit: {{ cancelInTransitFormData.dn_code }}</div>
          <q-space />
          <q-btn dense flat icon="close" v-close-popup>
            <q-tooltip content-class="bg-amber text-black shadow-4" :offset="[10, 10]">{{ $t('index.close') }}</q-tooltip>
          </q-btn>
        </q-bar>
        <q-card-section style="max-height: 325px; width: 400px" class="scroll">
          <div class="text-caption text-grey-7 q-mb-sm">This closes the in-transit DN and releases its outbound staging slot.</div>
          <q-input
            v-model="cancelInTransitFormData.cancellation_note"
            type="textarea"
            outlined
            square
            autofocus
            label="Cancellation reason"
            :rules="[val => !!String(val || '').trim() || 'A cancellation reason is required']"
          />
        </q-card-section>
        <div style="float: right; padding: 15px 15px 15px 0">
          <q-btn color="white" text-color="black" style="margin-right: 25px" @click="cancelInTransitDataCancel()">{{ $t('cancel') }}</q-btn>
          <q-btn color="negative" @click="cancelInTransitDataSubmit()">Cancel In Transit</q-btn>
        </div>
      </q-card>
    </q-dialog>
  </div>
</template>
<router-view />

<script>
import { getauth, postauth, putauth, deleteauth, ViewPrintAuth } from 'boot/axios_request'
import { LocalStorage } from 'quasar'
import StagingSlotPicker from '../../components/StagingSlotPicker.vue'

export default {
  name: 'Pagednlist',
  components: {
    StagingSlotPicker
  },
  data () {
    return {
      openid: '',
      login_name: '',
      authin: '0',
      pathname: 'dn/',
      pathname_previous: '',
      pathname_next: '',
      separator: 'cell',
      loading: false,
      height: '',
      table_list: [],
      viewprint_table: [],
      bar_code: '',
      pickinglist_print_table: [],
      pickinglist_check: 0,
      warehouse_detail: {},
      customer_list: [],
      customer_list1: [],
      driver_list: [],
      customer_detail: {},
      columns: [
        { name: 'dn_code', required: true, label: 'DN', align: 'left', field: 'dn_code', style: 'width: 130px', headerStyle: 'width: 130px' },
        { name: 'dn_status', label: this.$t('outbound.view_dn.dn_status'), field: 'dn_status', align: 'center', style: 'width: 115px', headerStyle: 'width: 115px' },
        { name: 'customer', label: this.$t('outbound.view_dn.customer'), field: 'customer', align: 'left', style: 'width: 135px', headerStyle: 'width: 135px' },
        { name: 'sku_summary', label: 'SKU / QTY', field: 'sku_summary', align: 'left', style: 'width: 170px', headerStyle: 'width: 170px' },
        { name: 'dispatch_driver', label: 'Driver', field: 'dispatch_driver', align: 'left', style: 'width: 100px', headerStyle: 'width: 100px' },
        { name: 'staging_bin', label: 'Staging', field: 'staging_bin', align: 'left', style: 'width: 135px', headerStyle: 'width: 135px' },
        { name: 'delivery_exception', label: 'Exception', field: 'delivery_exception', align: 'left', style: 'width: 105px', headerStyle: 'width: 105px' },
        { name: 'next_step', label: 'Next Step', field: 'next_step', align: 'left', style: 'width: 155px', headerStyle: 'width: 155px' },
        { name: 'update_time', label: this.$t('updatetime'), field: 'update_time', align: 'center', style: 'width: 155px', headerStyle: 'width: 155px' },
        { name: 'action', label: this.$t('action'), align: 'right', style: 'width: 84px', headerStyle: 'width: 84px' }
      ],
      filter: '',
      pagination: {
        page: 1,
        rowsPerPage: '30'
      },
      newForm: false,
      options1: [],
      isEdit: false,
      listNumber: '',
      options: LocalStorage.getItem('goods_code_list'),
      driver_options: LocalStorage.getItem('driver_name_list'),
      newdn: { creater: '' },
      newFormData: {
        dn_code: '',
        customer: '',
        goods_code: [],
        goods_qty: [],
        creater: ''
      },
      pickFormData: {
        dn_code: '',
        customer: '',
        goodsData: [],
        creater: ''
      },
      goodsData1: { bin: '', code: '', qty: '' },
      goodsData2: { bin: '', code: '', qty: '' },
      goodsData3: { bin: '', code: '', qty: '' },
      goodsData4: { bin: '', code: '', qty: '' },
      goodsData5: { bin: '', code: '', qty: '' },
      goodsData6: { bin: '', code: '', qty: '' },
      goodsData7: { bin: '', code: '', qty: '' },
      goodsData8: { bin: '', code: '', qty: '' },
      goodsData9: { bin: '', code: '', qty: '' },
      goodsData10: { bin: '', code: '', qty: '' },
      editid: 0,
      editFormData: {},
      pickedForm: false,
      pickedid: 0,
      deleteForm: false,
      deleteid: 0,
      neworderForm: false,
      neworderid: 0,
      orderreleaseForm: false,
      orderreleaseid: 0,
      viewForm: false,
      viewPLForm: false,
      viewdn: '',
      viewid: 0,
      dispatchid: 0,
      dispatchForm: false,
      dispatchFormData: {
        dn_code: '',
        driver: '',
        staging_bin: ''
      },
      podid: 0,
      podForm: false,
      podFormData: {
        dn_code: '',
        customer: '',
        goodsData: []
      },
      cancelInTransitForm: false,
      cancelInTransitId: 0,
      cancelInTransitFormData: {
        dn_code: '',
        cancellation_note: ''
      },
      printObj: {
        id: 'printMe',
        popTitle: this.$t('outbound.dn')
      },
      printPL: {
        id: 'printPL',
        popTitle: this.$t('outbound.pickinglist')
      },
      error1: this.$t('baseinfo.view_customer.error1'),
      error2: this.$t('notice.valerror'),
      isError1: false,
      isError2: false,
      current: 1,
      max: 0,
      total: 0,
      paginationIpt: 1
    }
  },
  methods: {
    statusLabel (status) {
      const labels = {
        1: this.$t('outbound.freshorder'),
        2: this.$t('outbound.neworder'),
        3: this.$t('outbound.pickstock'),
        4: this.$t('outbound.pickedstock'),
        5: this.$t('outbound.shippedstock'),
        6: this.$t('outbound.received'),
        7: 'Cancelled'
      }
      return labels[Number(status)] || 'N/A'
    },
    nextStepLabel (status) {
      const nextSteps = {
        1: this.$t('confirmorder'),
        2: this.$t('releaseorder'),
        3: this.$t('confirmpicked'),
        4: this.$t('dispatch'),
        5: this.$t('outbound.pod'),
        6: 'Complete',
        7: 'Cancelled'
      }
      return nextSteps[Number(status)] || 'Review'
    },
    normalizeRows (rows) {
      return (rows || []).map(item => {
        const statusCode = Number(item.dn_status)
        return {
          ...item,
          dn_status_code: statusCode,
          dn_status: this.statusLabel(statusCode),
          next_step: this.nextStepLabel(statusCode)
        }
      })
    },
    canAction (row, action) {
      const status = Number(row.dn_status_code)
      if (action === 'confirm' || action === 'edit' || action === 'delete') return status === 1
      if (action === 'release') return status === 2
      if (action === 'print') return status >= 3 && status <= 5
      if (action === 'pick') return status === 3
      if (action === 'dispatch') return status === 4
      if (action === 'pod') return status === 5
      if (action === 'cancel_intransit') {
        return status === 5 && LocalStorage.getItem('staff_type') === 'Admin'
      }
      return false
    },
    validate1 (val) {
      const reg = /^\d+$/g
      const check = reg.test(val)
      if (check) {
        this.isError1 = false
      } else {
        this.isError1 = true
      }
    },
    validate2 (val1, val2) {
      const reg = /^[0-9]\d*$/g
      const check = reg.test(val1)
      if (check && val1 <= val2) {
        this.isError2 = false
      } else {
        this.isError2 = true
      }
    },
    getList () {
      var _this = this
      if (LocalStorage.has('auth')) {
        getauth(_this.pathname + 'list/' + '?page=' + '' + _this.current, {})
          .then(res => {
            _this.table_list = []
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
            _this.table_list = _this.normalizeRows(res.results)
            res.results.forEach(item => {
              if (item.asn_status === 1) {
                item.asn_status = _this.$t()
              }
            })
            _this.customer_list = res.customer_list
            _this.customer_list1 = res.customer_list
            _this.pathname_previous = res.previous
            _this.pathname_next = res.next
          })
          .catch(err => {
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
      if (LocalStorage.has('auth')) {
        _this.current = 1
        _this.paginationIpt = 1
        getauth(_this.pathname + 'list/?dn_code__icontains=' + _this.filter + '&page=' + '' + _this.current, {})
          .then(res => {
            _this.table_list = []
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
            _this.table_list = _this.normalizeRows(res.results)
            _this.customer_list = res.customer_list
            _this.customer_list1 = res.customer_list
            _this.pathname_previous = res.previous
            _this.pathname_next = res.next
          })
          .catch(err => {
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
      if (LocalStorage.has('auth')) {
        getauth(_this.pathname_previous, {})
          .then(res => {
            _this.table_list = []
            _this.table_list = _this.normalizeRows(res.results)
            _this.customer_list = res.customer_list
            _this.customer_list1 = res.customer_list
            _this.pathname_previous = res.previous
            _this.pathname_next = res.next
          })
          .catch(err => {
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
      if (LocalStorage.has('auth')) {
        getauth(_this.pathname_next, {})
          .then(res => {
            _this.table_list = []
            _this.table_list = _this.normalizeRows(res.results)
            _this.customer_list = res.customer_list
            _this.customer_list1 = res.customer_list
            _this.pathname_previous = res.previous
            _this.pathname_next = res.next
          })
          .catch(err => {
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
      _this.table_list = []
      _this.getList()
    },
    newFormOpen () {
      var _this = this
      _this.isEdit = false
      _this.goodsDataClear()
      _this.newForm = true
      _this.newdn.creater = _this.login_name
      postauth(_this.pathname + 'list/', _this.newdn)
        .then(res => {
          if (!res.detail) {
            _this.newFormData.dn_code = res.dn_code
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    newDataSubmit () {
      var _this = this
      _this.newFormData.creater = _this.login_name
      let cancelRequest = false
      if (_this.newFormData.customer !== '') {
        _this.newFormData.goods_code = []
        _this.newFormData.goods_qty = []
        let goodsDataCheck = 0
        for (let i = 0; i < 10; i++) {
          const goodsData = `goodsData${i + 1}`
          if (_this[goodsData].code !== '' && _this[goodsData].qty !== '') {
            if (_this[goodsData].qty < 1) {
              cancelRequest = true
              _this.$q.notify({
                message: 'Total Quantity Must Be > 0',
                icon: 'close',
                color: 'negative'
              })
            } else {
              _this.newFormData.goods_code.push(_this[goodsData].code)
              _this.newFormData.goods_qty.push(_this[goodsData].qty)
            }
            goodsDataCheck += 1
          }
        }
        if (goodsDataCheck === 0) {
          cancelRequest = true
          _this.$q.notify({
            message: 'Please Enter The Goods & Qty',
            icon: 'close',
            color: 'negative'
          })
        }
      } else {
        cancelRequest = true
        _this.$q.notify({
          message: 'Please Enter The Customer',
          icon: 'close',
          color: 'negative'
        })
      }
      if (!cancelRequest) {
        postauth(_this.pathname + 'detail/', _this.newFormData)
          .then(res => {
            _this.table_list = []
            _this.getList()
            _this.newDataCancel()
            if (res.detail === 'success') {
              _this.$q.notify({
                message: 'Success Create',
                icon: 'check',
                color: 'green'
              })
            }
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            })
          })
      }
    },
    newDataCancel () {
      var _this = this
      _this.newForm = false
      _this.newFormData = {
        dn_code: '',
        customer: '',
        goods_code: [],
        goods_qty: [],
        creater: ''
      }
      _this.goodsDataClear()
    },
    goodsDataClear () {
      var _this = this
      for (let i = 1; i <= 10; i++) {
        _this[`goodsData${i}`] = { code: '', qty: '' }
      }
    },
    editData (e) {
      var _this = this
      _this.isEdit = true
      _this.goodsDataClear()
      if (e.dn_status !== _this.$t('outbound.freshorder')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Not ' + _this.$t('outbound.freshorder'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.newFormData.dn_code = e.dn_code
        _this.newFormData.customer = e.customer
        getauth(_this.pathname + 'detail/?dn_code=' + e.dn_code).then(res => {
          _this.newForm = true
          _this.editid = e.id
          res.results.forEach((detail, index) => {
            _this[`goodsData${index + 1}`] = { code: detail.goods_code, qty: detail.goods_qty }
          })
        })
      }
    },
    editDataSubmit () {
      var _this = this
      _this.newFormData.creater = _this.login_name
      let cancelRequest = false
      if (_this.newFormData.customer !== '') {
        _this.newFormData.goods_code = []
        _this.newFormData.goods_qty = []
        let goodsDataCheck = 0
        for (let i = 0; i < 10; i++) {
          const goodsData = `goodsData${i + 1}`
          if (_this[goodsData].code !== '' && _this[goodsData].qty !== '') {
            if (_this[goodsData].qty < 1) {
              cancelRequest = true
              _this.$q.notify({
                message: 'Total Quantity Must Be > 0',
                icon: 'close',
                color: 'negative'
              })
            } else {
              _this.newFormData.goods_code.push(_this[goodsData].code)
              _this.newFormData.goods_qty.push(_this[goodsData].qty)
            }
            goodsDataCheck += 1
          }
        }
        if (goodsDataCheck === 0) {
          cancelRequest = true
          _this.$q.notify({
            message: 'Please Enter The Goods & Qty',
            icon: 'close',
            color: 'negative'
          })
        }
      } else {
        cancelRequest = true
        _this.$q.notify({
          message: 'Please Enter The Customer',
          icon: 'close',
          color: 'negative'
        })
      }
      if (!cancelRequest) {
        putauth(_this.pathname + 'detail/', _this.newFormData)
          .then(res => {
            _this.table_list = []
            _this.editDataCancel()
            _this.getList()
            if (!res.detail) {
              _this.$q.notify({
                message: 'Success Edit DN',
                icon: 'check',
                color: 'green'
              })
            }
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            })
          })
      }
    },
    editDataCancel () {
      var _this = this
      _this.newForm = false
      _this.editid = 0
      _this.newFormData = {
        dn_code: '',
        customer: '',
        goods_code: [],
        goods_qty: [],
        creater: ''
      }
      _this.goodsDataClear()
    },
    deleteData (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.freshorder')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.freshorder'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.deleteForm = true
        _this.deleteid = e.id
      }
    },
    deleteDataSubmit () {
      var _this = this
      deleteauth(_this.pathname + 'list/' + _this.deleteid + '/')
        .then(res => {
          _this.table_list = []
          _this.deleteDataCancel()
          _this.getList()
          if (!res.detail) {
            _this.$q.notify({
              message: 'Success Delete DN',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    deleteDataCancel () {
      var _this = this
      _this.deleteForm = false
      _this.deleteid = 0
    },
    neworderData (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.freshorder')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.freshorder'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.neworderForm = true
        _this.neworderid = e.id
      }
    },
    neworderDataSubmit () {
      var _this = this
      postauth(_this.pathname + 'neworder/' + _this.neworderid + '/', {})
        .then(res => {
          _this.table_list = []
          _this.neworderDataCancel()
          _this.getList()
          if (!res.detail) {
            _this.$q.notify({
              message: 'Success Confirm DN Delivery',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    neworderDataCancel () {
      var _this = this
      _this.neworderForm = false
      _this.neworderid = 0
    },
    orderreleaseData (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.neworder')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.neworder'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.orderreleaseForm = true
        _this.orderreleaseid = e.id
      }
    },
    orderreleaseAllData () {
      var _this = this
      _this.$q.dialog({
        title: 'Release ready orders',
        message: 'Release all confirmed orders into picking. Continue?',
        cancel: true,
        persistent: true
      }).onOk(() => {
        postauth(_this.pathname + 'orderrelease/', {})
          .then(res => {
            _this.table_list = []
            _this.getList()
            if (!res.detail) {
              _this.$q.notify({
                message: 'Ready orders released',
                icon: 'check',
                color: 'green'
              })
            }
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            })
          })
      })
    },
    orderreleaseDataSubmit () {
      var _this = this
      putauth(_this.pathname + 'orderrelease/' + _this.orderreleaseid + '/', {})
        .then(res => {
          _this.table_list = []
          _this.orderreleaseDataCancel()
          _this.getList()
          if (!res.detail) {
            _this.$q.notify({
              message: 'Success Release DN Code',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    orderreleaseDataCancel () {
      var _this = this
      _this.orderreleaseForm = false
      _this.orderreleaseid = 0
    },
    getFocus (number) {
      this.listNumber = number
    },
    setOptions (val) {
      const _this = this
      if (!val) {
        _this[`goodsData${_this.listNumber}`].code = ''
      }
      const needle = val.toLowerCase()
      getauth('goods/?goods_code__icontains=' + needle).then(res => {
        const goodscodelist = []
        for (let i = 0; i < res.results.length; i++) {
          goodscodelist.push(res.results[i].goods_code)
          if (_this.listNumber) {
            if (res.results[i].goods_code === val) {
              _this[`goodsData${_this.listNumber}`].code = val
            }
          }
        }
        _this.options1 = goodscodelist
      })
    },
    filterFn (val, update, abort) {
      if (val.length < 1) {
        abort()
        return
      }
      update(() => {
        this.options = this.options1
      })
    },
    setModel (val) {
      const _this = this
      _this.newFormData.customer = val
    },
    filterFnS (val, update, abort) {
      var _this = this
      update(() => {
        const needle = val.toLocaleLowerCase()
        const dataFilter = _this.customer_list1
        _this.customer_list = dataFilter.filter(v => v.toLocaleLowerCase().indexOf(needle) > -1)
      })
    },
    PrintPickingList (e) {
      var _this = this
      var QRCode = require('qrcode')
      QRCode.toDataURL(e.bar_code, [
        {
          errorCorrectionLevel: 'H',
          mode: 'byte',
          version: '2',
          type: 'image/jpeg'
        }
      ])
        .then(url => {
          _this.bar_code = url
        })
        .catch(err => {
          console.error(err)
        })
      _this.viewPLForm = true
      getauth(_this.pathname + 'pickinglist/' + e.id + '/')
        .then(res => {
          _this.pickinglist_print_table = []
          _this.picklist_check = 0
          res.forEach(item => {
            if (item.picked_qty > 0) {
              _this.picklist_check += 1
            } else {
            }
          })
          _this.pickinglist_print_table = res
          _this.viewPLForm = true
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    pickedData (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.pickstock')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.pickstock'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.pickFormData.dn_code = e.dn_code
        _this.pickFormData.customer = e.customer
        getauth(_this.pathname + 'pickinglist/' + e.id + '/').then(res => {
          _this.pickedForm = true
          _this.pickedid = e.id
          _this.pickFormData.goodsData = res
        })
      }
    },
    pickedDataSubmit () {
      var _this = this
      _this.pickFormData.creater = _this.login_name
      postauth(_this.pathname + 'picked/' + _this.pickedid + '/', _this.pickFormData)
        .then(res => {
          _this.table_list = []
          _this.pickedDataCancel()
          _this.getList()
          if (!res.detail) {
            _this.$q.notify({
              message: 'Success Confirm Picking List',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    pickedDataCancel () {
      var _this = this
      _this.pickedForm = false
      _this.pickedid = 0
      _this.pickFormData = {
        dn_code: '',
        customer: '',
        goodsData: [],
        creater: ''
      }
      _this.goodsDataClear()
    },
    viewData (e) {
      var _this = this
      ViewPrintAuth(_this.pathname + 'viewprint/' + e.id + '/').then(res => {
        _this.viewprint_table = res.dn_detail
        _this.warehouse_detail = res.warehouse_detail
        _this.customer_detail = res.customer_detail
        _this.viewdn = e.dn_code
        var QRCode = require('qrcode')
        QRCode.toDataURL(e.bar_code, [
          {
            errorCorrectionLevel: 'H',
            mode: 'byte',
            version: '2',
            type: 'image/jpeg'
          }
        ])
          .then(url => {
            _this.bar_code = url
          })
          .catch(err => {
            console.error(err)
          })
        _this.viewForm = true
      })
    },
    filterFnDispatch (val, update, abort) {
      var _this = this
      if (val.length < 1) {
        abort()
        return
      }
      update(() => {
        _this.loadDispatchDriverOptions(val)
      })
    },
    loadDispatchDriverOptions (needle = '') {
      const query = needle ? '?driver_name__icontains=' + encodeURIComponent(needle) : '?page=1'
      getauth('driver/' + query)
        .then(res => {
          const driverNames = (res.results || []).map(item => item.driver_name).filter(Boolean)
          LocalStorage.set('driver_name_list', driverNames)
          this.driver_options = driverNames
        })
        .catch(err => {
          this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    DispatchDN (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.pickedstock')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.pickedstock'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.dispatchFormData.dn_code = e.dn_code
        _this.dispatchFormData.staging_bin = ''
        _this.dispatchid = e.id
        _this.loadDispatchDriverOptions()
        _this.dispatchForm = true
      }
    },
    dispatchDataCancel () {
      var _this = this
      _this.dispatchFormData = { dn_code: '', driver: '', staging_bin: '' }
      _this.dispatchForm = false
    },
    dispatchDataSubmit () {
      var _this = this
      postauth(_this.pathname + 'dispatch/' + _this.dispatchid + '/', _this.dispatchFormData)
        .then(res => {
          _this.table_list = []
          _this.dispatchDataCancel()
          _this.getList()
          if (!res.detail) {
            _this.$q.notify({
              message: 'Success Dispatch',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          _this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    },
    PODData (e) {
      var _this = this
      if (e.dn_status !== _this.$t('outbound.shippedstock')) {
        _this.$q.notify({
          message: e.dn_code + ' DN Status Is Not ' + _this.$t('outbound.shippedstock'),
          icon: 'close',
          color: 'negative'
        })
      } else {
        _this.podFormData.dn_code = e.dn_code
        _this.podFormData.customer = e.customer
        getauth(_this.pathname + 'detail/?dn_code=' + e.dn_code).then(res => {
          _this.podForm = true
          _this.podid = e.id
          _this.podFormData.goodsData = (res.results || []).map(item => ({
            ...item,
            expected_delivery_qty: Number(item.intransit_qty || 0),
            intransit_qty: Number(item.intransit_qty || 0),
            delivery_damage_qty: Number(item.delivery_damage_qty || 0),
            delivery_note: item.delivery_note || ''
          }))
        })
      }
    },
    PODDataCancel () {
      var _this = this
      _this.podForm = false
      _this.podid = 0
      _this.podFormData = {
        dn_code: '',
        customer: '',
        goodsData: []
      }
    },
    PODDataSubmit () {
      var _this = this
      const invalidExceptionNotes = (_this.podFormData.goodsData || []).some(item => {
        const expected = Number(item.expected_delivery_qty || 0)
        const actual = Number(item.intransit_qty)
        const damage = Number(item.delivery_damage_qty || 0)
        return (actual !== expected || damage > 0) && !String(item.delivery_note || '').trim()
      })
      if (invalidExceptionNotes) {
        _this.$q.notify({
          message: 'Add an exception note for shortage, more quantity, or damage',
          icon: 'close',
          color: 'negative'
        })
        return
      }
      if (!(_this.isError1 || _this.isError2)) {
        postauth(_this.pathname + 'pod/' + _this.podid + '/', _this.podFormData)
          .then(res => {
            _this.table_list = []
            _this.PODDataCancel()
            _this.getList()
            if (!res.detail) {
              _this.$q.notify({
                message: 'Proof of delivery recorded',
                icon: 'check',
                color: 'green'
              })
            }
          })
          .catch(err => {
            _this.$q.notify({
              message: err.detail,
              icon: 'close',
              color: 'negative'
            })
          })
      }
    },
    cancelInTransitData (row) {
      if (!this.canAction(row, 'cancel_intransit')) {
        this.$q.notify({
          message: 'Only an administrator can cancel an in-transit DN',
          icon: 'close',
          color: 'negative'
        })
        return
      }
      this.cancelInTransitId = row.id
      this.cancelInTransitFormData = {
        dn_code: row.dn_code,
        cancellation_note: ''
      }
      this.cancelInTransitForm = true
    },
    cancelInTransitDataCancel () {
      this.cancelInTransitForm = false
      this.cancelInTransitId = 0
      this.cancelInTransitFormData = {
        dn_code: '',
        cancellation_note: ''
      }
    },
    cancelInTransitDataSubmit () {
      const note = String(this.cancelInTransitFormData.cancellation_note || '').trim()
      if (!note) {
        this.$q.notify({
          message: 'A cancellation reason is required',
          icon: 'close',
          color: 'negative'
        })
        return
      }
      postauth(this.pathname + 'cancel-intransit/' + this.cancelInTransitId + '/', {
        cancellation_note: note
      })
        .then(res => {
          this.cancelInTransitDataCancel()
          this.getList()
          if (!res.detail) {
            this.$q.notify({
              message: 'In-transit DN canceled and staging released',
              icon: 'check',
              color: 'green'
            })
          }
        })
        .catch(err => {
          this.$q.notify({
            message: err.detail,
            icon: 'close',
            color: 'negative'
          })
        })
    }
  },
  created () {
    var _this = this
    if (LocalStorage.has('openid')) {
      _this.openid = LocalStorage.getItem('openid')
    } else {
      _this.openid = ''
      LocalStorage.set('openid', '')
    }
    if (LocalStorage.has('login_name')) {
      _this.login_name = LocalStorage.getItem('login_name')
    } else {
      _this.login_name = ''
      LocalStorage.set('login_name', '')
    }
    if (LocalStorage.has('auth')) {
      _this.authin = '1'
      _this.table_list = []
      _this.getList()
    } else {
      _this.authin = '0'
    }
    if (LocalStorage.has('goods_code_list')) {
    } else {
      LocalStorage.set('goods_code_list', [])
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
  updated () {},
  destroyed () {}
}
</script>

<style scoped>
.outbound-nowrap {
  white-space: nowrap;
}

.outbound-action-cell {
  white-space: nowrap;
  min-width: 84px;
}

.outbound-pod-card {
  min-width: 500px;
}
</style>
