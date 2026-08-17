<template>
  <q-page class="cli-install-page q-pa-md">
    <q-card bordered flat class="cli-install-card">
      <q-card-section class="row items-center q-pb-sm">
        <div>
          <div class="text-h5 text-weight-bold">GreaterWMS CLI</div>
          <div class="text-subtitle2 text-grey-7">Install once and use the same API and safety controls as the web platform.</div>
        </div>
        <q-space />
        <q-btn flat round icon="refresh" :loading="loading" aria-label="Refresh" @click="loadManifest" />
      </q-card-section>

      <q-separator />

      <q-card-section v-if="error">
        <q-banner dense class="bg-red-1 text-negative">{{ error }}</q-banner>
      </q-card-section>

      <template v-if="manifest">
        <q-card-section class="row q-col-gutter-md q-pb-none">
          <div class="col-12 col-md-6">
            <div class="cli-label">Web</div>
            <a :href="manifest.web_url" target="_blank" rel="noopener">{{ manifest.web_url }}</a>
          </div>
          <div class="col-12 col-md-6">
            <div class="cli-label">Runtime</div>
            <div>{{ manifest.cli.runtime.recommended }}</div>
          </div>
        </q-card-section>

        <q-card-section>
          <div class="cli-section-title">Install</div>
          <div class="cli-command" v-for="command in manifest.cli.install_commands" :key="command">
            <code>{{ command }}</code>
            <q-btn flat round dense icon="content_copy" aria-label="Copy command" @click="copy(command)" />
          </div>
          <div class="text-caption text-grey-7 q-mt-sm">The CLI requires Node.js {{ manifest.cli.runtime.node_min }} or newer.</div>
        </q-card-section>

        <q-card-section>
          <div class="cli-section-title">Login</div>
          <div v-for="auth in manifest.cli.auth" :key="auth.role" class="cli-auth-row q-mb-md">
            <div class="cli-label">{{ auth.role }}</div>
            <div class="cli-command">
              <code>{{ auth.command }}</code>
              <q-btn flat round dense icon="content_copy" aria-label="Copy command" @click="copy(auth.command)" />
            </div>
            <div class="text-caption text-grey-7">{{ auth.credential }}. The credential is prompted and is not saved locally.</div>
          </div>
        </q-card-section>

        <q-card-section>
          <div class="cli-section-title">First commands</div>
          <div class="cli-command" v-for="command in manifest.cli.first_commands" :key="command">
            <code>{{ command }}</code>
            <q-btn flat round dense icon="content_copy" aria-label="Copy command" @click="copy(command)" />
          </div>
        </q-card-section>

        <q-card-section>
          <div class="cli-section-title">Safety</div>
          <ul class="cli-safety q-my-none q-pl-md">
            <li v-for="item in manifest.cli.safety" :key="item">{{ item }}</li>
          </ul>
        </q-card-section>

        <q-card-section class="text-caption text-grey-7 q-pt-none">
          AI agents can read the machine-readable installation manifest at
          <code>{{ manifest.api_base_url }}/cli/install/</code>.
        </q-card-section>
      </template>
    </q-card>
  </q-page>
</template>

<script>
import { copyToClipboard } from 'quasar'
import { get } from 'boot/axios_request'

export default {
  name: 'CliInstall',
  data () {
    return {
      loading: false,
      error: '',
      manifest: null
    }
  },
  mounted () {
    this.loadManifest()
  },
  methods: {
    async loadManifest () {
      this.loading = true
      this.error = ''
      try {
        this.manifest = await get('cli/install/')
      } catch (error) {
        this.error = 'The CLI installation manifest is unavailable. Please refresh or contact an administrator.'
      } finally {
        this.loading = false
      }
    },
    copy (value) {
      copyToClipboard(value)
        .then(() => this.$q.notify({ message: 'Copied', color: 'positive', timeout: 1000 }))
        .catch(() => this.$q.notify({ message: 'Copy failed', color: 'negative' }))
    }
  }
}
</script>

<style scoped>
.cli-install-page {
  background: #f4f6f8;
}

.cli-install-card {
  max-width: 980px;
  margin: 0 auto;
}

.cli-section-title {
  color: #263238;
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 10px;
}

.cli-label {
  color: #607d8b;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .04em;
  text-transform: uppercase;
  margin-bottom: 4px;
}

.cli-command {
  align-items: center;
  background: #263238;
  border-radius: 3px;
  color: #fff;
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
  min-height: 36px;
  padding-left: 12px;
}

.cli-command code {
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.cli-command .q-btn {
  color: #fff;
  flex: 0 0 auto;
}

.cli-safety li {
  margin-bottom: 6px;
}
</style>
