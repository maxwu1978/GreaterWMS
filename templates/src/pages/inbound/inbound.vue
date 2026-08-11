<template>
  <q-page class="flex flex-top">
<template>
  <div class="q-pa-md">
    <div class="q-gutter-y-md" style="max-width: 100%">
      <q-tabs
        v-model="detaillink"
      >
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="asn" :label="$t('inbound.asn')" icon="img:statics/inbound/asn.png" :to="{ name: 'asn' }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="packlist" :label="$t('inbound.packlist')" icon="description" :to="{ name: 'packlist' }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="predeliverystock" :label="$t('inbound.predeliverystock')" icon="img:statics/inbound/polist.png" :to="{ name: 'asn', query: { asn_status: '1' } }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="preloadstock" :label="$t('inbound.preloadstock')" icon="img:statics/inbound/preloadstock.png" :to="{ name: 'asn', query: { asn_status: '2' } }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="presortstock" :label="$t('inbound.presortstock')" icon="img:statics/inbound/presortstock.png" :to="{ name: 'asn', query: { asn_status: '3' } }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="sortstock" :label="$t('inbound.sortstock')" icon="img:statics/inbound/sortstock.png" :to="{ name: 'asn', query: { asn_status: '4' } }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="shortage" :label="$t('inbound.shortage')" icon="img:statics/inbound/shortage.png" :to="{ name: 'shortage' }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="more" :label="$t('inbound.more')" icon="img:statics/inbound/more.png" :to="{ name: 'more' }" exact/>
        </transition>
        <transition appear enter-active-class="animated zoomIn">
          <q-route-tab name="asnfinish" :label="$t('inbound.asnfinish')" icon="img:statics/inbound/asnfinish.png" :to="{ name: 'asn', query: { asn_status: '5' } }" exact/>
        </transition>
      </q-tabs>
    </div>
  </div>
</template>
    <div class="main-table">
      <router-view />
    </div>
  </q-page>
</template>

<script>
export default {
  name: 'Pageinbound',
  data () {
    return {
      detaillink: 'asn'
    }
  },
  methods: {
  }
}
</script>
