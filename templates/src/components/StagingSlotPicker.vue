<template>
  <div class="staging-slot-picker">
    <div class="text-caption text-grey-7 q-mb-sm">
      {{ helperText }}
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
            :outline="!isSelected(slot.bin_name)"
            :color="slot.occupied ? 'grey-6' : (slot.reserved ? 'amber-7' : (isSelected(slot.bin_name) ? 'primary' : 'positive'))"
            :disable="slot.occupied || (slot.reserved && !allowReserved) || (!isSelected(slot.bin_name) && multiple && maxSelections > 0 && selected.length >= maxSelections)"
            :label="String(slot.slot).padStart(2, '0')"
            @click="selectSlot(slot)"
          >
            <q-tooltip v-if="slot.occupied || (slot.reserved && !allowReserved)">
              {{ slot.occupied ? 'Occupied' : 'Reserved' }}: {{ slot.assignment.reference_code }}
            </q-tooltip>
          </q-btn>
        </div>
      </div>
    </div>
    <div v-if="selected.length" class="text-primary text-caption q-mt-sm">
      Selected {{ selected.length }}: {{ selected.join(', ') }}
    </div>
  </div>
</template>

<script>
import { getauth } from 'boot/axios_request'

export default {
  name: 'StagingSlotPicker',
  props: {
    flow: { type: String, required: true },
    value: { type: [String, Array], default: '' },
    multiple: { type: Boolean, default: false },
    maxSelections: { type: Number, default: 1 },
    allowReserved: { type: Boolean, default: false }
  },
  data () {
    return {
      loading: false,
      slots: [],
      selected: this.normalize(this.value)
    }
  },
  computed: {
    helperText () {
      return this.flow === 'OUTBOUND'
        ? 'Select the staging slot used for this shipment.'
        : 'Select staging slots for unloading.'
    },
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
      this.selected = this.normalize(value)
    }
  },
  methods: {
    normalize (value) {
      if (Array.isArray(value)) return value.slice()
      return value ? [value] : []
    },
    isSelected (binName) {
      return this.selected.indexOf(binName) !== -1
    },
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
      if (this.multiple) {
        const index = this.selected.indexOf(slot.bin_name)
        if (index >= 0) {
          this.selected.splice(index, 1)
        } else {
          if (this.maxSelections > 0 && this.selected.length >= this.maxSelections) return
          this.selected.push(slot.bin_name)
        }
        this.$emit('input', this.selected.slice())
      } else {
        this.selected = [slot.bin_name]
        this.$emit('input', slot.bin_name)
      }
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
