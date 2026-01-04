from fabric.bluetooth import BluetoothClient, BluetoothDevice
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.scrolledwindow import ScrolledWindow

import modules.icons as icons


class BluetoothDeviceSlot(CenterBox):
    def __init__(self, device: BluetoothDevice, paired_box: Box, available_box: Box, **kwargs):
        super().__init__(name="bluetooth-device", **kwargs)
        self.device = device
        self.paired_box = paired_box
        self.available_box = available_box
        self.device.connect("changed", self.on_changed)
        self.device.connect(
            "notify::closed", lambda *_: self.device.closed and self.destroy()
        )

        self.connection_label = Label(name="bluetooth-connection", markup=icons.bluetooth_disconnected)
        self.battery_label = Label(name="bluetooth-battery", visible=False)
        self.connect_button = Button(
            name="bluetooth-connect",
            label="Connect",
            on_clicked=lambda *_: self.device.set_connecting(not self.device.connected),
            style_classes=["connected"] if self.device.connected else None,
        )

        self.start_children = [
            Box(
                spacing=8,
                h_expand=True,
                h_align="fill",
                children=[
                    Image(icon_name=device.icon_name + "-symbolic", size=16),
                    Label(label=device.name, h_expand=True, h_align="start", ellipsization="end"),
                    self.connection_label,
                ],
            )
        ]
        self.end_children = Box(spacing=6, children=[self.battery_label, self.connect_button])

        self.device.emit("changed")

    def on_changed(self, *_):
        self.connection_label.set_markup(
            icons.bluetooth_connected if self.device.connected else icons.bluetooth_disconnected
        )
        if self.device.connecting:
            self.connect_button.set_label(
                "Connecting..." if not self.device.connecting else "..."
            )
        else:
            self.connect_button.set_label(
                "Connect" if not self.device.connected else "Disconnect"
            )
        if self.device.connected:
            self.connect_button.add_style_class("connected")
        else:
            self.connect_button.remove_style_class("connected")
        self._ensure_correct_container()
        self.update_battery_label()
        return

    def _ensure_correct_container(self) -> None:
        target = self.paired_box if self.device.paired else self.available_box
        parent = self.get_parent()
        if parent is target:
            return
        if parent and hasattr(parent, "remove"):
            parent.remove(self)
        target.add(self)

    def update_battery_label(self) -> None:
        if not self.device.connected:
            self.battery_label.set_visible(False)
            return
        pct = self._get_battery_percentage()
        if pct is None:
            self.battery_label.set_visible(False)
            return
        pct = max(0, min(100, pct))
        self.battery_label.set_visible(True)
        self.battery_label.set_markup(f"{icons.battery} {pct:.0f}%")

    def _get_battery_percentage(self):
        # BluetoothDevice exposes battery-percentage / battery-level when available
        for attr in ("battery_percentage", "battery_level"):
            if hasattr(self.device, attr):
                try:
                    value = getattr(self.device, attr)
                    value = value() if callable(value) else value
                    if value is None:
                        continue
                    return float(value)
                except Exception:
                    continue
        return None

class BluetoothConnections(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="bluetooth",
            spacing=4,
            orientation="vertical",
            **kwargs,
        )

        self._device_slots: list[BluetoothDeviceSlot] = []

        self.widgets = kwargs["widgets"]

        self.buttons = self.widgets.buttons.bluetooth_button
        self.bt_status_text = self.buttons.bluetooth_status_text
        self.bt_status_button = self.buttons.bluetooth_status_button
        self.bt_icon = self.buttons.bluetooth_icon
        self.bt_label = self.buttons.bluetooth_label
        self.bt_menu_button = self.buttons.bluetooth_menu_button
        self.bt_menu_label = self.buttons.bluetooth_menu_label

        self.client = BluetoothClient(on_device_added=self.on_device_added)
        self.scan_label = Label(name="bluetooth-scan-label", markup=icons.radar)
        self.scan_button = Button(
            name="bluetooth-scan",
            child=self.scan_label,
            tooltip_text="Scan for Bluetooth devices",
            on_clicked=lambda *_: self.client.toggle_scan()
        )
        self.back_button = Button(
            name="bluetooth-back",
            child=Label(name="bluetooth-back-label", markup=icons.chevron_left),
            on_clicked=lambda *_: self.widgets.show_notif()
        )

        self.client.connect("notify::enabled", lambda *_: self.status_label())
        self.client.connect(
            "notify::scanning",
            lambda *_: self.update_scan_label()
        )

        self.paired_box = Box(spacing=2, orientation="vertical")
        self.available_box = Box(spacing=2, orientation="vertical")

        content_box = Box(spacing=4, orientation="vertical")
        content_box.add(self.paired_box)
        content_box.add(Label(name="bluetooth-section", label="Ready to be paired"))
        content_box.add(self.available_box)

        self.children = [
            CenterBox(
                name="bluetooth-header",
                start_children=self.back_button,
                center_children=Label(name="bluetooth-text", label="Bluetooth Devices"),
                end_children=self.scan_button
            ),
            ScrolledWindow(
                name="bluetooth-devices",
                min_content_size=(-1, -1),
                child=content_box,
                v_expand=True,
                propagate_width=False,
                propagate_height=False,
            ),
        ]

        self.client.notify("scanning")
        self.client.notify("enabled")

    def status_label(self):
        print(self.client.enabled)
        if self.client.enabled:
            for i in [self.bt_status_button, self.bt_status_text, self.bt_icon, self.bt_label, self.bt_menu_button, self.bt_menu_label]:
                i.remove_style_class("disabled")
            self.bt_icon.set_markup(icons.bluetooth)
            self.update_connected_status()
        else:
            self.bt_status_text.set_label("Disabled")
            for i in [self.bt_status_button, self.bt_status_text, self.bt_icon, self.bt_label, self.bt_menu_button, self.bt_menu_label]:
                i.add_style_class("disabled")
            self.bt_icon.set_markup(icons.bluetooth_off)

    def on_device_added(self, client: BluetoothClient, address: str):
        if not (device := client.get_device(address)):
            return
        slot = BluetoothDeviceSlot(device, self.paired_box, self.available_box)
        self._device_slots.append(slot)
        device.connect("changed", lambda *_: self.update_connected_status())

        if device.paired:
            return self.paired_box.add(slot)
        return self.available_box.add(slot)

    def update_connected_status(self):
        if not self.client.enabled:
            self.bt_status_text.set_label("Disabled")
            return

        name = self._get_first_connected_name()
        if name:
            self.bt_status_text.set_label(name)
        else:
            self.bt_status_text.set_label("Enabled")

    def _get_first_connected_name(self):
        for box in (self.paired_box, self.available_box):
            for child in box.get_children():
                try:
                    if isinstance(child, BluetoothDeviceSlot) and child.device.connected:
                        return child.device.name
                except Exception:
                    continue
        return None

    def update_scan_label(self):
        if self.client.scanning:
            self.scan_label.add_style_class("scanning")
            self.scan_button.add_style_class("scanning")
            self.scan_button.set_tooltip_text("Stop scanning for Bluetooth devices")
        else:
            self.scan_label.remove_style_class("scanning")
            self.scan_button.remove_style_class("scanning")
            self.scan_button.set_tooltip_text("Scan for Bluetooth devices")
