<template>
  <q-table
    class="operations-board__table"
    table-class="operations-board__grid"
    :data="rows"
    :columns="columns"
    :row-key="rowKey"
    dense
    flat
    bordered
    separator="horizontal"
    hide-bottom
    :row-class="rowClass"
    :loading="loading"
    :pagination="pagination"
    :no-data-label="noDataLabel"
    v-bind="$attrs"
    v-on="$listeners"
  >
    <template v-for="(slotScope, slotName) in $scopedSlots" v-slot:[slotName]="props">
      <slot :name="slotName" v-bind="props" />
    </template>
  </q-table>
</template>

<script>
export default {
  name: 'GreaterWmsOperationsTable',
  inheritAttrs: false,
  props: {
    rows: { type: Array, default: () => [] },
    columns: { type: Array, default: () => [] },
    rowKey: { type: [String, Function], default: 'id' },
    rowClass: { type: [String, Function], default: undefined },
    loading: { type: Boolean, default: false },
    pagination: { type: Object, default: () => ({ rowsPerPage: 0 }) },
    noDataLabel: { type: String, default: '' }
  }
}
</script>
