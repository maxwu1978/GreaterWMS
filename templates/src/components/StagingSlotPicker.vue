<template>
  <div class="staging-slot-picker">
    <div class="text-caption text-grey-7 q-mb-sm">
      Select one available staging slot. Reserved and occupied slots are unavailable.
    </div>
    <div v-if="loading" class="text-grey q-pa-sm">Loading staging occupancy...</div>
    <div v-for="zone in zones" :key="zone.name" class="q-mb-md">
      <div class="row items-center q-mb-xs">
        <div class="text-subtitle2">{{ zone.name }}</div>
        <q-space />
        <div class="text-caption text-grey-7">{{ zone.available }}/20 available</div>
      </div>
      <div class="row q-col-gutter-xs">
        <div v-for="slot in zone.slots" :key="slot.bin_name" class="col-3 col-sm-2">
          <q-btn
            class="full-width"
            dense
            no-caps
            :outline="selected !== slot.bin_name"
            :color="slot.occupied ? 'grey-6' : (slot.reserved ? 'amber-7' : (selected === slot.bin_name ? 'primary' : 'positive'))"
            :disable="slot.occupied || slot.reserved"
            :label="String(slot.slot).padStart(2, '0')"
            @click="selectSlot(slot)"
          >
            <q-tooltip v-if="slot.occupied || slot.reserved">
              {{ slot.occupied ? 'Occupied' : 'Reserved' }}: {{ slot.assignment.reference_code }}
            </q-tooltip>
          </q-btn>
        </div>
      </div>
    </div>
    <div v-if="selected" class="text-primary text-caption q-mt-sm">
      Selected: {{ selected }}
    </div>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request'

export default {
  name: 'StagingSlotPicker',
  props: {
    flow: { type: String, required: true },
    value: { type: String, default: '' }
  },
  data () {
    return {
      loading: false,
      slots: [],
      selected: this.value
    }
  },
  computed: {
    zones () {
      return ['STAGE-LEFT', 'STAGE-RIGHT'].map(name => {
        const slots = this.slots.filter(slot => slot.zone === name)
        return {
          name,
          slots,
          available: slots.filter(slot => slot.available).length
        }
      })
    }
  },
  watch: {
    value (value) {
      this.selected = value
    }
  },
  methods: {
    load () {
      this.loading = true
      getauth('staging/slots/?flow=' + encodeURIComponent(this.flow))
        .then(res => {
          this.slots = res
        })
        .catch(() => {})
        .finally(() => {
          this.loading = false
        })
    },
    selectSlot (slot) {
      this.selected = slot.bin_name
      this.$emit('input', slot.bin_name)
      this.$emit('select', slot)
    },
    refresh () {
      this.load()
    }
  },
  mounted () {
    this.load()
  }
}
</script>
