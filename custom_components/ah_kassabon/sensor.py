"""Sensors for AH Kassabon."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import KassabonConfigEntry, prices
from .const import DOMAIN, SIGNAL_UPDATED

TOP_N = 15


async def async_setup_entry(
    hass: HomeAssistant, entry: KassabonConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities(
        [
            LatestReceiptSensor(entry),
            MoreExpensiveSensor(entry),
            AverageChangeSensor(entry),
        ]
    )


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: KassabonConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self.key}"
        self._attr_translation_key = self.key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="AH Kassabon",
            manufacturer="Albert Heijn (kassabonnen)",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._summary: dict[str, Any] = {}

    key = ""

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATED, self._refresh))
        self._refresh()

    @callback
    def _refresh(self) -> None:
        self._summary = prices.summary(self._entry.runtime_data.data)
        self.async_write_ha_state()


def _short(change: dict[str, Any]) -> dict[str, Any]:
    return {
        "product": change["name"],
        "van": change["first_price"],
        "naar": change["price"],
        "verschil": change["diff"],
        "procent": change["pct"],
        "sinds": change["first_when"][:10],
    }


class LatestReceiptSensor(_Base):
    key = "latest_receipt"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:receipt-text-outline"

    @property
    def native_value(self) -> datetime | None:
        latest = self._summary.get("latest_receipt")
        if not latest:
            return None
        return dt_util.as_local(datetime.fromisoformat(latest["when"]).replace(tzinfo=dt_util.get_default_time_zone()))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        latest = self._summary.get("latest_receipt") or {}
        return {
            "kassabon_id": self._summary.get("latest_receipt_id"),
            "totaal": latest.get("total"),
            "winkel": latest.get("store"),
            "regels": len(latest.get("items", [])),
            "aantal_kassabonnen": self._summary.get("receipts", 0),
        }


class MoreExpensiveSensor(_Base):
    key = "more_expensive"
    _attr_icon = "mdi:trending-up"
    _attr_native_unit_of_measurement = "producten"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        return len(self._summary.get("more_expensive", []))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "goedkoper": len(self._summary.get("cheaper", [])),
            "gevolgd": self._summary.get("tracked", 0),
            "producten": self._summary.get("products", 0),
            "top": [_short(c) for c in self._summary.get("more_expensive", [])[:TOP_N]],
        }


class AverageChangeSensor(_Base):
    key = "average_change"
    _attr_icon = "mdi:cart-percent"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self) -> float | None:
        return self._summary.get("average_pct")
