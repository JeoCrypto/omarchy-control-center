import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons
import qs.Commons as Commons

// Control Center: one bar button that opens the everyday toggles and sliders.
// State comes from bin/control-center (JSON), which also performs the actions,
// so every control here is a thin view over that script.
//
// Colour is used sparingly: the bar icon and idle controls are monochrome, and
// only a control that is switched on gets a tinted disc. Tints come from the
// active Omarchy theme.
//
// Optional setting in the widget's shell.json entry:
//   "showNetworkName": false   show "Connected" instead of the Wi-Fi name
Panel {
  id: root
  moduleName: "io.github.jeocrypto.control-center"
  ipcTarget: "io.github.jeocrypto.control-center"
  // This panel owns its IPC target so it can add `refresh` to the usual verbs:
  //   omarchy-shell io.github.jeocrypto.control-center refresh
  manageIpc: false

  ShellIpc {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    // Re-read every control now, e.g. after a script changed one of them.
    function refresh(): void { root.refresh() }
  }
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  // The backend ships inside the plugin folder; run it through bash so it works
  // even if the executable bit was lost on the way.
  readonly property string backendPath: Qt.resolvedUrl("bin/control-center").toString().replace(/^file:\/\//, "")
  readonly property bool showNetworkName: String(setting("showNetworkName", true)) !== "false"
  readonly property color fg: bar ? bar.foreground : Commons.Color.foreground
  readonly property color bg: bar ? bar.background : Commons.Color.background
  readonly property string iconFont: bar ? bar.fontFamily : "sans-serif"

  // Tints for switched-on controls, read from the active theme's colors.toml
  // (blue, magenta, yellow, green). These defaults are used until it loads.
  property color blue: "#7fa4c9"
  property color violet: "#c49ac4"
  property color amber: "#e9b96e"
  property color green: "#9fbf7a"

  FileView {
    id: themeColors
    path: Quickshell.env("HOME") + "/.local/state/omarchy/current/theme/colors.toml"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      const raw = text()
      const pick = (key, fallback) => {
        const m = raw.match(new RegExp("^" + key + "\\s*=\\s*\"(#[0-9a-fA-F]{6})\"", "m"))
        return m ? m[1] : fallback
      }
      root.blue = pick("blue", root.blue)
      root.violet = pick("magenta", root.violet)
      root.amber = pick("yellow", root.amber)
      root.green = pick("green", root.green)
    }
  }

  // A theme switch replaces the theme folder, which drops the file watch.
  Timer { interval: 5000; running: root.opened; repeat: true; onTriggered: themeColors.reload() }

  property var status: ({ wifi: false, ssid: "", bluetooth: false, dnd: false, nightlight: false,
                          awake: false, brightness: null, volume: 0, muted: false, glass: "" })
  property real brightness: 50
  property real volume: 0

  function tint(c, a) { return Qt.rgba(c.r, c.g, c.b, a) }
  function glyph(code) { return String.fromCodePoint(code) }

  // ---- State ----
  function refresh() { probe.start() }

  // Every backend run is time-limited with capped output (BoundedRun), so a
  // stalled network or audio tool can't hold the shell or pile up processes.
  BoundedRun {
    id: probe
    seconds: 6
    maxBytes: 16384
    argv: ["bash", root.backendPath, "status"]
    onFinished: function(exitCode, output) {
      if (exitCode !== 0) return
      try {
        const raw = JSON.parse(output)
        // Take only the fields the panel knows, in the types it expects. The
        // network name comes from outside this machine: keep it short.
        const next = {
          wifi: raw.wifi === true, ssid: String(raw.ssid || "").slice(0, 64), bluetooth: raw.bluetooth === true,
          dnd: raw.dnd === true, nightlight: raw.nightlight === true, awake: raw.awake === true,
          brightness: typeof raw.brightness === "number" ? Math.max(0, Math.min(100, raw.brightness)) : null,
          volume: typeof raw.volume === "number" ? Math.max(0, Math.min(100, raw.volume)) : 0,
          muted: raw.muted === true,
          glass: ["clear", "glass", "frosted", "solid"].indexOf(raw.glass) >= 0 ? raw.glass : ""
        }
        root.status = next
        // Never fight the pointer: a slider being dragged keeps its own value.
        if (!root.brightnessBusy && next.brightness !== null) root.brightness = next.brightness
        if (!root.volumeBusy) root.volume = next.volume
      } catch (e) {}
    }
  }

  Timer { interval: 2500; running: root.opened; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
  Timer { id: settle; interval: 450; onTriggered: root.refresh() }

  // ---- Actions ----
  // Flip the value locally so the control answers the click at once, then let
  // the next status read confirm it.
  function toggle_(key) {
    const next = Object.assign({}, root.status)
    next[key === "mute" ? "muted" : key] = !next[key === "mute" ? "muted" : key]
    root.status = next
    runAction([key])
  }

  function setGlass(level) {
    const next = Object.assign({}, root.status)
    next.glass = level
    root.status = next
    runAction(["glass", level])
  }

  // Switches run one at a time through an owned, time-limited process. When
  // it ends, successfully or not, the controls are read again, so a switch
  // that failed goes back to what the system really says.
  property var actionQueue: []
  function runAction(args) {
    if (actionQueue.length >= 8) return
    actionQueue = actionQueue.concat([args])
    pumpActions()
  }
  function pumpActions() {
    if (action.running || actionQueue.length === 0) return
    const args = actionQueue[0]
    actionQueue = actionQueue.slice(1)
    action.start(["bash", root.backendPath].concat(args))
  }
  BoundedRun {
    id: action
    seconds: 8
    maxBytes: 4096
    onFinished: { if (root.actionQueue.length > 0) root.pumpActions(); else settle.restart() }
  }

  // Sliders send at most one command at a time; the latest value waits its turn.
  property int brightnessPending: -1
  property int volumePending: -1
  property bool brightnessDragging: false
  property bool volumeDragging: false
  readonly property bool brightnessBusy: brightnessDragging || brightnessProc.running || brightnessPending >= 0
  readonly property bool volumeBusy: volumeDragging || volumeProc.running || volumePending >= 0

  function setBrightness(v) {
    root.brightness = v
    root.brightnessPending = Math.max(1, Math.round(v))
    pumpBrightness()
  }
  function pumpBrightness() {
    if (brightnessProc.running || root.brightnessPending < 0) return
    const value = String(root.brightnessPending)
    root.brightnessPending = -1
    brightnessProc.start(["bash", root.backendPath, "brightness", value])
  }
  BoundedRun { id: brightnessProc; seconds: 4; maxBytes: 4096; onFinished: root.pumpBrightness() }

  function setVolume(v) {
    root.volume = v
    root.volumePending = Math.round(v)
    pumpVolume()
  }
  function pumpVolume() {
    if (volumeProc.running || root.volumePending < 0) return
    const value = String(root.volumePending)
    root.volumePending = -1
    volumeProc.start(["bash", root.backendPath, "volume", value])
  }
  BoundedRun { id: volumeProc; seconds: 4; maxBytes: 4096; onFinished: root.pumpVolume() }

  // ---- Bar button ----
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.glyph(0xF062E)   // tune (sliders)
    tooltipText: strings.t("title")
    onPressed: function(b) { root.toggle() }
  }

  // ---- Panel ----
  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: panel.loadedContent
    contentWidth: panel.fittedContentWidth(Style.space(336))
    contentHeight: panel.fittedContentHeight(panel.loadedContentHeight, Style.space(560))

    content: PanelKeyCatcher {
      implicitHeight: column.implicitHeight
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Column {
        id: column
        width: parent.width
        spacing: Style.space(10)

        // Connectivity: two wide tiles
        Row {
          width: parent.width
          spacing: Style.space(10)

          WideTile {
            width: (parent.width - parent.spacing) / 2
            icon: root.glyph(root.status.wifi ? 0xF05A9 : 0xF05AA)
            title: strings.t("wifi")
            subtitle: !root.status.wifi ? strings.t("off")
              : !root.status.ssid ? strings.t("not-connected")
              : root.showNetworkName ? root.status.ssid : strings.t("connected")
            on: root.status.wifi
            tintColor: root.blue
            onActivated: root.toggle_("wifi")
          }

          WideTile {
            width: (parent.width - parent.spacing) / 2
            icon: root.glyph(root.status.bluetooth ? 0xF00AF : 0xF00B2)
            title: strings.t("bluetooth")
            subtitle: root.status.bluetooth ? strings.t("on") : strings.t("off")
            on: root.status.bluetooth
            tintColor: root.blue
            onActivated: root.toggle_("bluetooth")
          }
        }

        // Modes: three small tiles
        Row {
          width: parent.width
          spacing: Style.space(10)
          readonly property real tileWidth: (width - spacing * 2) / 3

          SmallTile {
            width: parent.tileWidth
            icon: root.glyph(root.status.dnd ? 0xF009B : 0xF009A)
            title: strings.t("dnd")
            on: root.status.dnd
            tintColor: root.violet
            onActivated: root.toggle_("dnd")
          }

          SmallTile {
            width: parent.tileWidth
            icon: root.glyph(0xF0594)
            title: strings.t("nightlight")
            on: root.status.nightlight
            tintColor: root.amber
            onActivated: root.toggle_("nightlight")
          }

          SmallTile {
            width: parent.tileWidth
            icon: root.glyph(0xF0176)
            title: strings.t("awake")
            on: root.status.awake
            tintColor: root.green
            onActivated: root.toggle_("awake")
          }
        }

        // Display brightness
        SliderCard {
          visible: root.status.brightness !== null
          title: strings.t("display")
          icon: root.glyph(0xF00E0)
          value: root.brightness
          minimum: 1
          onMoved: function(v) { root.setBrightness(v) }
          onDraggingChanged: root.brightnessDragging = dragging
        }

        // Sound volume; the speaker icon mutes
        SliderCard {
          title: strings.t("sound")
          icon: root.glyph(root.status.muted || root.volume < 1 ? 0xF0581 : root.volume < 50 ? 0xF0580 : 0xF057E)
          dimmed: root.status.muted
          value: root.volume
          iconClickable: true
          onIconClicked: root.toggle_("mute")
          onMoved: function(v) { root.setVolume(v) }
          onDraggingChanged: root.volumeDragging = dragging
        }

        // Glass level: only when the optional glass-level command is installed
        Card {
          visible: root.status.glass !== ""
          width: parent.width
          implicitHeight: glassColumn.implicitHeight + Style.space(20)

          Column {
            id: glassColumn
            x: Style.space(12)
            y: Style.space(10)
            width: parent.width - Style.space(24)
            spacing: Style.space(8)

            Label { text: strings.t("glass"); strong: true }

            Row {
              id: glassRow
              width: parent.width
              spacing: Style.space(6)
              readonly property var levels: ["clear", "glass", "frosted", "solid"]

              Repeater {
                model: glassRow.levels

                Rectangle {
                  id: segment
                  required property string modelData
                  readonly property bool current: root.status.glass === modelData
                  width: (glassRow.width - glassRow.spacing * 3) / 4
                  height: Style.space(26)
                  radius: Style.space(8)
                  color: current ? root.tint(root.fg, 0.9) : root.tint(root.fg, segmentHover.hovered ? 0.14 : 0.07)
                  Behavior on color { ColorAnimation { duration: Style.duration(120) } }

                  Text {
                    anchors.centerIn: parent
                    textFormat: Text.PlainText
                    text: strings.t("glass." + segment.modelData)
                    color: segment.current ? root.bg : root.fg
                    font.pixelSize: Style.font.bodySmall
                    font.weight: segment.current ? Font.DemiBold : Font.Normal
                  }

                  HoverHandler { id: segmentHover; cursorShape: Qt.PointingHandCursor }
                  TapHandler { onTapped: root.setGlass(segment.modelData) }
                }
              }
            }
          }
        }
      }
    }
  }

  // ---- Building blocks ----
  component Card: Rectangle {
    radius: Style.space(14)
    color: root.tint(root.fg, 0.06)
    border.width: 1
    border.color: root.tint(root.fg, 0.06)
  }

  component Label: Text {
    property bool strong: false
    textFormat: Text.PlainText
    color: strong ? root.fg : root.tint(root.fg, 0.6)
    font.pixelSize: strong ? Style.font.body : Style.font.bodySmall
    font.weight: strong ? Font.DemiBold : Font.Normal
    elide: Text.ElideRight
  }

  // The round icon: neutral when off, softly tinted when on.
  component Disc: Rectangle {
    property string icon: ""
    property bool on: false
    property color tintColor: root.blue
    width: Style.space(32)
    height: width
    radius: width / 2
    color: on ? tintColor : root.tint(root.fg, 0.12)
    Behavior on color { ColorAnimation { duration: Style.duration(150) } }

    Text {
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: parent.icon
      color: parent.on ? root.bg : root.fg
      font.family: root.iconFont
      font.pixelSize: Style.font.title + 2
    }
  }

  component WideTile: Card {
    id: wide
    property string icon: ""
    property string title: ""
    property string subtitle: ""
    property bool on: false
    property color tintColor: root.blue
    signal activated()
    implicitHeight: Style.space(56)
    scale: wideTap.pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Style.duration(100); easing.type: Easing.OutCubic } }

    Disc {
      id: wideDisc
      x: Style.space(12)
      anchors.verticalCenter: parent.verticalCenter
      icon: wide.icon
      on: wide.on
      tintColor: wide.tintColor
    }

    Column {
      anchors.left: wideDisc.right
      anchors.leftMargin: Style.space(10)
      anchors.right: parent.right
      anchors.rightMargin: Style.space(10)
      anchors.verticalCenter: parent.verticalCenter
      spacing: 1
      Label { width: parent.width; text: wide.title; strong: true }
      Label { width: parent.width; text: wide.subtitle }
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { id: wideTap; onTapped: wide.activated() }
  }

  component SmallTile: Card {
    id: small
    property string icon: ""
    property string title: ""
    property bool on: false
    property color tintColor: root.blue
    signal activated()
    implicitHeight: Style.space(76)
    scale: smallTap.pressed ? 0.97 : 1
    Behavior on scale { NumberAnimation { duration: Style.duration(100); easing.type: Easing.OutCubic } }

    Disc {
      id: smallDisc
      anchors.horizontalCenter: parent.horizontalCenter
      y: Style.space(11)
      icon: small.icon
      on: small.on
      tintColor: small.tintColor
    }

    Label {
      anchors.top: smallDisc.bottom
      anchors.topMargin: Style.space(7)
      x: Style.space(4)
      width: parent.width - Style.space(8)
      horizontalAlignment: Text.AlignHCenter
      text: small.title
      color: root.fg
    }

    HoverHandler { cursorShape: Qt.PointingHandCursor }
    TapHandler { id: smallTap; onTapped: small.activated() }
  }

  component SliderCard: Card {
    id: sliderCard
    property string title: ""
    property string icon: ""
    property real value: 0
    property real minimum: 0
    property bool dimmed: false
    property bool iconClickable: false
    readonly property bool dragging: slider.dragging
    signal moved(real value)
    signal iconClicked()
    width: parent ? parent.width : 0
    implicitHeight: Style.space(64)

    Label {
      x: Style.space(12)
      y: Style.space(10)
      text: sliderCard.title
      strong: true
    }

    Text {
      id: sliderIcon
      x: Style.space(12)
      anchors.verticalCenter: slider.verticalCenter
      width: Style.space(20)
      textFormat: Text.PlainText
      text: sliderCard.icon
      color: root.tint(root.fg, sliderCard.dimmed ? 0.45 : 0.85)
      font.family: root.iconFont
      font.pixelSize: Style.font.title + 2

      HoverHandler { enabled: sliderCard.iconClickable; cursorShape: Qt.PointingHandCursor }
      TapHandler { enabled: sliderCard.iconClickable; onTapped: sliderCard.iconClicked() }
    }

    PanelSlider {
      id: slider
      anchors.left: sliderIcon.right
      anchors.leftMargin: Style.space(6)
      anchors.right: parent.right
      anchors.rightMargin: Style.space(12)
      y: Style.space(32)
      bar: root.bar
      opacity: sliderCard.dimmed ? 0.5 : 1
      minimum: sliderCard.minimum
      maximum: 100
      step: 5
      integer: true
      value: sliderCard.value
      onMoved: function(v) { sliderCard.moved(v) }
    }
  }
}
