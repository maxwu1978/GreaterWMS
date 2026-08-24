# iOS and iPadOS Build Runbook

This runbook records the first Capacitor-based native shell for MaxSmart WMS.
It is a universal iOS app target, so the same Xcode project supports iPhone
and iPad.

## Current State

- Native project: `frontend/ios/App/App.xcodeproj`
- Bundle identifier: `online.maxsmartwms.app`
- Display name: `MaxSmart WMS`
- Web source: existing Vite React app in `frontend`
- Native wrapper: Capacitor
- Minimum iOS deployment target: `15.0`
- Simulator proof point: iPad Pro 13-inch (M5), iOS 26.2
- 2026-05-03 status: plan item 4 is complete for documentation ownership. The Capacitor build path, simulator proof point, real-device readiness notes, and iPhone/iPad validation checklist are documented here.

The native shell is intentionally thin. The WMS business logic still lives in
the web app, and the iOS app packages the production build into a WebView.

## Build Commands

Run from `frontend`:

```bash
npm run build:ios
npm run ios:sync
npm run ios:build:sim
```

`build:ios` always injects production endpoints:

```text
VITE_API_BASE_URL=https://api.maxsmartwms.online/api/v1
VITE_WS_BASE_URL=wss://api.maxsmartwms.online
```

Do not build the native app with the default relative `/api/v1` base URL. In a
Capacitor WebView, that would point at the local app origin instead of the WMS
API service.

## Backend Requirements

The backend CORS allowlist must include the native WebView origins:

```text
capacitor://localhost
ionic://localhost
```

The scanner WebSocket must use the API host, not `window.location.host`, because
the native app location host is local to the WebView.

Mutation endpoints used from the native shell must send
`X-Idempotency-Key`. Offline or weak-network confirmations should enter the
same IndexedDB outbox as the browser app and replay only when the same tenant
and signed-in user are active again.

## iOS Permissions

`frontend/ios/App/App/Info.plist` includes:

- `NSCameraUsageDescription`
- `NSPhotoLibraryUsageDescription`
- `ITSAppUsesNonExemptEncryption=false`

The current scanner supports live camera scanning, manual scanner-gun input, and
photo barcode decoding. Production release still needs real iPad/iPhone hardware
validation because Web `BarcodeDetector` support can vary by iOS version.

## Verified Locally

On 2026-05-03:

- `npm run build:ios` passed.
- `npm run lint -- --quiet` passed after ignoring generated Capacitor web
  assets.
- Backend settings import confirmed the mobile CORS origins.
- Production CORS preflight for `Origin: capacitor://localhost` passed after
  updating the Render `CORS_ORIGINS` runtime variable.
- `xcodebuild` built `App.app` for the iPad Pro 13-inch (M5) simulator.
- The app installed and launched in the iPad simulator.
- `xcodebuild` also built the app for generic `iphoneos` / arm64 with
  `CODE_SIGNING_ALLOWED=NO`, confirming the native project compiles for real
  iPhone and iPad hardware.

## Real Device Validation

The real-device pass is the next release gate. Use it to confirm behavior that
the simulator cannot prove, especially camera access, barcode detection, and
touch ergonomics in warehouse flows.

Add these weak-network checks to the real-device pass:

1. Start Receiving, disable network, confirm one package, and verify the app
   shows a queued-work notice instead of a red dead-end error.
2. Re-enable network and verify the receipt syncs once, the package list
   refreshes, and inventory is not double-counted.
3. Repeat the same offline confirm tap twice and verify only one queued action
   is shown for the current tenant/user.
4. Disconnect/reconnect while the scanner view is open and verify the scanner
   socket recovers without an app restart.

## Mobile Receiving Automation

The repeatable mobile receiving smoke is:

```bash
cd frontend
npm run uat:mobile-receiving
```

The script creates a verified temporary tenant, opens the receiving flow with an
iPhone 14 Pro Max viewport, types a tracking code, verifies the compact mobile
layout, confirms the dock/staging location is surfaced near the active package,
checks for horizontal overflow, and confirms one package receipt. It defaults to
production URLs and can be pointed at staging or localhost with:

```bash
WMS_AUDIT_APP_URL=http://localhost:5173 \
WMS_AUDIT_API_URL=https://api.maxsmartwms.online/api/v1 \
npm run uat:mobile-receiving
```

For real-device screenshots on iOS 26, `devicectl` can confirm install, launch,
and process state. Visual capture still needs either manual screenshots or a
root-owned `pymobiledevice3 remote tunneld` session before
`pymobiledevice3 developer screenshot` can connect.

### Device Readiness

Current local check on 2026-05-03:

- Xcode: `26.2`
- Project signing style: automatic
- Bundle identifier: `online.maxsmartwms.app`
- Target device family: `1,2` (iPhone and iPad)
- Deployment target: `15.0`
- `xcrun devicectl` detected `Max 2024`, an iPhone 14 Pro Max on iOS 26.3.1,
  as paired and available.
- `xcrun xctrace` initially reported the same device as offline, which usually
  clears after unlocking the phone or refreshing Xcode's Devices window.
- `iphoneos` / arm64 build without signing succeeded.
- Xcode account cache shows the active Personal Team as `8479L9J2ZQ`
  (`wu max (Personal Team)`).
- Signed real-device build succeeded with `DEVELOPMENT_TEAM=8479L9J2ZQ`.
- Xcode created `iOS Team Provisioning Profile: online.maxsmartwms.app`.
- `xcrun devicectl device install app` installed the app on `Max 2024`.
- First launch was blocked by iOS because the personal developer profile has
  not yet been trusted on the device.
- After trusting the developer profile on the iPhone, `xcrun devicectl device
  process launch` started `online.maxsmartwms.app` successfully.
- `xcrun devicectl device info processes` confirmed the native `App.app/App`
  process running on the device.
- 2026-05-03 follow-up: the compact mobile receiving build was signed and
  installed on `Max 2024`. Command-line launch was blocked only because the
  device was locked; open the app manually after unlocking, or rerun
  `devicectl device process launch` while the device is unlocked.

Local signing identities found:

```text
Apple Development: wuqingxin1978@icloud.com (2M6ZPV2H33)
Apple Development: wuqxmark@gmail.com (4TBBCD9JLG)
```

The signing identity used by the successful build is:

```text
Apple Development: wuqxmark@gmail.com (4TBBCD9JLG)
```

Note that the command-line `DEVELOPMENT_TEAM` must use the active Xcode account
team ID (`8479L9J2ZQ`), not the certificate suffix.

If a device appears offline in `xcrun xctrace list devices`, handle these first:

1. Unlock the iPhone or iPad and keep it on the Home Screen.
2. Connect by USB or enable wireless debugging from Xcode's Devices window.
3. Tap **Trust This Computer** on the device if prompted.
4. In Xcode, open **Window > Devices and Simulators** and wait until the device
   changes from offline to available.
5. Confirm with:

```bash
xcrun xctrace list devices
```

### Build and Install

Run from `frontend`:

```bash
npm run ios:sync
open ios/App/App.xcodeproj
```

In Xcode:

1. Select the `App` target.
2. Open **Signing & Capabilities**.
3. Add or refresh the Apple ID under **Xcode > Settings > Accounts**.
4. Choose the Apple Developer Team.
5. Confirm Xcode creates a Development provisioning profile for
   `online.maxsmartwms.app`.
6. Select the connected iPhone or iPad as the run destination.
7. Press **Run**.

If the command line is preferred after signing is configured, use:

```bash
xcodebuild \
  -project ios/App/App.xcodeproj \
  -scheme App \
  -configuration Debug \
  -sdk iphoneos \
  -destination 'id=00008120-0012549A3663C01E' \
  DEVELOPMENT_TEAM=8479L9J2ZQ \
  CODE_SIGN_STYLE=Automatic \
  -allowProvisioningUpdates \
  -allowProvisioningDeviceRegistration \
  build
```

Install and launch with:

```bash
APP_PATH="$HOME/Library/Developer/Xcode/DerivedData/App-dhschgeecgxvvbeozhvbwqvztewu/Build/Products/Debug-iphoneos/App.app"
xcrun devicectl device install app \
  --device 77C4A30C-F11D-54D4-899B-D7D51ABB588C \
  "$APP_PATH"
xcrun devicectl device process launch \
  --device 77C4A30C-F11D-54D4-899B-D7D51ABB588C \
  online.maxsmartwms.app \
  --terminate-existing
```

If launch fails with `profile has not been explicitly trusted by the user`,
trust the developer profile on the iPhone:

1. Open **Settings** on the iPhone.
2. Go to **General > VPN & Device Management**.
3. Open the developer app profile for `wuqxmark@gmail.com` or `wu max`.
4. Tap **Trust**.
5. Re-run the `devicectl device process launch` command.

After trust, the expected launch result is:

```text
Launched application with online.maxsmartwms.app bundle identifier.
```

The built-in `devicectl` command set can confirm install, launch, process, lock
state, and display metadata. It does not provide a direct screenshot command.
`pymobiledevice3 developer screenshot` was also checked, but on this iOS 26
device it requires a root-owned remote tunnel. For this reason, real-device UI
inspection currently needs either direct phone observation, Xcode's device
viewer, or a dedicated UI automation setup.

### Smoke Checklist

Record pass or fail for each item:

- App launches on a real iPhone.
- App launches on a real iPad.
- Login reaches the production API without CORS or network errors.
- Session survives app background and foreground.
- Receiving opens and shows live inbound work.
- Manual scan input works with expected receiving labels and tracking codes.
- Camera scan requests permission, opens the camera, and decodes a test label.
- Read photo requests permission and decodes a saved label image.
- Putaway, picking, and shipping scan fields accept scanner-gun input.
- Touch targets are usable with gloves or quick warehouse operation.
- Portrait and landscape layouts do not hide primary actions.
- Logout and relaunch return to the correct authentication state.

Failing camera or photo items should be treated as a native release blocker. If
Web `BarcodeDetector` is inconsistent on the target iOS version, replace that
path with a Capacitor native barcode scanner plugin before TestFlight.

### iPhone And iPad Validation Checklist

Use this checklist as the formal native mobile gate before TestFlight:

- Build and install the latest `build:ios` output on one real iPhone and one real iPad.
- Confirm both devices reach `https://api.maxsmartwms.online/api/v1` from the WebView without CORS, mixed-content, or relative-origin API errors.
- Run the operator path in portrait on iPhone: login, dashboard, receiving list, live receiving, manual scan entry, staging, confirm receipt, logout, and relaunch.
- Run the supervisor/table path on iPad in portrait and landscape: dashboard, receiving, putaway, inventory, picking, shipping, billing, clients, filters, tabs, and table/card overflow.
- Confirm camera permission, camera barcode decode, photo permission, and photo barcode decode with real labels or saved test-label images.
- Confirm scanner-gun/manual input focus works in receiving, putaway, picking, and shipping without the virtual keyboard blocking the primary action.
- Confirm app background/foreground preserves or intentionally resets the session, and that relaunch returns to the expected authentication state.
- Capture screenshots or written evidence for every failed native-only behavior, especially camera/photo scan, keyboard focus, overflow, and touch-target issues.

Native release sign-off requires the full checklist to pass, or an explicit release decision documenting any accepted non-blocking issue. Camera or photo barcode failure remains blocking unless the release switches to a native scanner plugin.

## Remaining Release Work

Before TestFlight or App Store distribution:

- Configure Apple Developer Team signing in Xcode.
- Confirm the bundle ID in Apple Developer / App Store Connect.
- Replace default generated app icons and launch artwork.
- Validate login, receiving, putaway, picking, shipping, camera scan, photo scan,
  and scanner-gun manual input on a real iPad.
- Confirm App Store privacy answers and export compliance.
- Decide whether the first native release keeps Web barcode detection or moves
  to a native barcode scanner plugin.
