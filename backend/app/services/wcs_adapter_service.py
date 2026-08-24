"""Adapter for WCS systems that accept transport tasks and send callbacks."""

from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import SKU
from app.models.task import AssignedType, Task, TaskStatus, TaskType
from app.models.warehouse import Location, LocationType, Warehouse
from app.models.wcs import WcsTaskBinding, WcsTaskBindingStatus
from app.services.agv_service import AGVService

WCS_STATUS_MAP = {
    -10: WcsTaskBindingStatus.CANCELLED.value,
    0: WcsTaskBindingStatus.QUEUED.value,
    5: WcsTaskBindingStatus.ASSIGNED.value,
    10: WcsTaskBindingStatus.ASSIGNED.value,
    20: WcsTaskBindingStatus.IN_PROGRESS.value,
    25: WcsTaskBindingStatus.PAUSED.value,
    30: WcsTaskBindingStatus.COMPLETED.value,
    40: WcsTaskBindingStatus.FAILED.value,
}


class WcsAdapterError(RuntimeError):
    """Raised when a WCS adapter operation cannot proceed safely."""

    def __init__(self, message: str | dict, detail: dict | None = None):
        if isinstance(message, dict) and detail is None:
            detail = message
            message = str(message.get("message") or "WCS adapter error")
        super().__init__(message)
        self.detail = detail


class WcsAdapterService:
    WCS_CERTIFICATION_REFERENCE_TYPE = "wcs_sandbox_cert"
    WCS_CERTIFICATION_ALLOWED_SCOPES = {
        "sandbox_certification",
        "normal_path_sandbox_certification",
    }
    WCS_CERTIFICATION_DEFAULT_SCOPE = "normal_path_sandbox_certification"
    WCS_CERTIFICATION_DEFAULT_LPN_PREFIX = "WCS-SBX-CERT"

    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def read_config(self, warehouse_id: str) -> dict:
        warehouse = await self.db.scalar(
            select(Warehouse).where(
                Warehouse.tenant_id == self.tenant_id,
                Warehouse.id == warehouse_id,
            )
        )
        if not warehouse:
            raise WcsAdapterError("Warehouse not found")
        config = self._wcs_config(warehouse)
        point_mappings = self._canonical_point_mappings(warehouse)
        return {
            "warehouse_id": warehouse.id,
            "warehouse_code": warehouse.code,
            "configured": bool(config),
            "config": self._redacted_wcs_config(config),
            "point_mapping_count": len(point_mappings),
            "point_mappings": list(point_mappings.values()),
        }

    async def preview_config_update(self, warehouse_id: str, changes: dict[str, Any]) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        existing = self._wcs_config(warehouse)
        proposed = self._merge_config_update(warehouse, existing, changes)
        validation = self._validate_config_update(proposed)
        return {
            "ok": validation["ok"],
            "dry_run": True,
            "writes": False,
            "action": "wcs.config.update.preview",
            "risk": "medium",
            "warehouse_id": warehouse.id,
            "changed_keys": self._changed_config_keys(existing, proposed),
            "current_config": self._redacted_wcs_config(existing),
            "proposed_config": self._redacted_wcs_config(proposed),
            "validation": validation,
            "confirmation_required_for_write": True,
            "next_action": (
                "fix_config_issues"
                if not validation["ok"]
                else "review_then_run_wcs_config_update_with_confirm_config"
            ),
        }

    async def update_config(self, warehouse_id: str, changes: dict[str, Any]) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        address = dict(warehouse.address or {})
        existing = dict(address.get("_wcs") or {})
        proposed = self._merge_config_update(warehouse, existing, changes)
        validation = self._validate_config_update(proposed)
        if not validation["ok"]:
            raise WcsAdapterError(
                {
                    "code": "wcs_config_update_blocked",
                    "message": "WCS config update failed validation",
                    "validation": validation,
                }
            )
        changed_keys = self._changed_config_keys(existing, proposed)
        address["_wcs"] = proposed
        warehouse.address = address
        await self.db.flush()
        return {
            "ok": True,
            "status": "configured",
            "action": "wcs.config.update",
            "warehouse_id": warehouse.id,
            "changed_keys": changed_keys,
            "config": self._redacted_wcs_config(proposed),
            "validation": validation,
            "next_action": "run_wcs_config_then_dispatch_preview",
        }

    async def list_bindings(
        self,
        *,
        warehouse_id: str | None = None,
        task_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict:
        query = select(WcsTaskBinding).where(WcsTaskBinding.tenant_id == self.tenant_id)
        if warehouse_id:
            query = query.where(WcsTaskBinding.warehouse_id == warehouse_id)
        if task_id:
            query = query.where(WcsTaskBinding.task_id == task_id)
        if status:
            query = query.where(WcsTaskBinding.status == status)
        rows = (
            await self.db.scalars(
                query.order_by(WcsTaskBinding.created_at.desc()).limit(max(1, min(limit, 100)))
            )
        ).all()
        return {"count": len(rows), "items": [self._binding_summary(row) for row in rows]}

    async def preview_dispatch_task(self, task_id: str, callback_url: str | None = None) -> dict:
        task, warehouse, source, destination = await self._load_task_context(task_id)
        existing = await self.db.scalar(
            select(WcsTaskBinding).where(
                WcsTaskBinding.tenant_id == self.tenant_id,
                WcsTaskBinding.task_id == task_id,
            )
        )
        gate = self.validate_dispatch_gate(task, warehouse, source, destination)
        payload = None
        if gate["ok"]:
            payload = self.build_transport_payload(
                task=task,
                warehouse=warehouse,
                source=source,
                destination=destination,
                callback_url=callback_url,
            )
        return {
            "ok": True,
            "dry_run": True,
            "action": "wcs.dispatch",
            "entity": {"type": "task", "id": task.id, "warehouse_id": warehouse.id},
            "gate": gate,
            "already_dispatched": bool(existing and existing.wcs_task_id),
            "binding": self._binding_summary(existing) if existing else None,
            "planned_request": {
                "endpoint": "POST /task/wlTaskInfo/addTransportTask",
                "body": payload,
                "external_wcs_call": False,
            },
            "confirmation_required_for_write": True,
            "next_action": "fix_gate_issues" if not gate["ok"] else "review_then_dispatch_from_controlled_operator_flow",
        }

    async def preview_certification_task(
        self,
        *,
        warehouse_id: str,
        source_location_id: str,
        destination_location_id: str,
        sku_id: str,
        quantity: int,
        certification_scope: str,
        reference_id: str | None,
        lpn_prefix: str | None,
    ) -> dict:
        planned = await self._build_certification_task_plan(
            warehouse_id=warehouse_id,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            sku_id=sku_id,
            quantity=quantity,
            certification_scope=certification_scope,
            reference_id=reference_id,
            lpn_prefix=lpn_prefix,
        )
        return {
            "ok": True,
            "dry_run": True,
            "writes": False,
            "action": "wcs.certification_task.preview",
            "risk": "medium",
            "entity": {
                "type": "warehouse",
                "id": planned["warehouse"].id,
                "warehouse_id": planned["warehouse"].id,
            },
            "certification_scope": planned["certification_scope"],
            "planned_task": planned["task_fields"],
            "planned_request": {
                "method": "POST",
                "endpoint": "/api/v1/integrations/wcs/certification-tasks/create",
                "body": {
                    "warehouse_id": warehouse_id,
                    "source_location_id": source_location_id,
                    "destination_location_id": destination_location_id,
                    "sku_id": sku_id,
                    "quantity": quantity,
                    "certification_scope": planned["certification_scope"],
                    "reference_id": planned["task_fields"]["reference_id"],
                    "lpn_prefix": planned["lpn_prefix"],
                    "confirm_create": True,
                },
                "external_wcs_call": False,
            },
            "confirmation_required_for_write": True,
            "next_action": "review_then_create_certification_task_with_confirm_flag",
        }

    async def create_certification_task(
        self,
        *,
        warehouse_id: str,
        source_location_id: str,
        destination_location_id: str,
        sku_id: str,
        quantity: int,
        certification_scope: str,
        reference_id: str | None,
        lpn_prefix: str | None,
        confirm_create: bool,
    ) -> dict:
        if not confirm_create:
            raise WcsAdapterError(
                {
                    "code": "confirm_create_required",
                    "message": "Certification task creation requires confirm_create=true after preview review.",
                }
            )
        planned = await self._build_certification_task_plan(
            warehouse_id=warehouse_id,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            sku_id=sku_id,
            quantity=quantity,
            certification_scope=certification_scope,
            reference_id=reference_id,
            lpn_prefix=lpn_prefix,
        )
        task = Task(**planned["task_fields"])
        self.db.add(task)
        await self.db.flush()
        return {
            "ok": True,
            "created": True,
            "action": "wcs.certification_task.create",
            "risk": "medium",
            "dry_run": False,
            "writes": True,
            "task": {
                "id": task.id,
                "tenant_id": task.tenant_id,
                "warehouse_id": task.warehouse_id,
                "task_type": task.task_type,
                "status": task.status,
                "assigned_type": task.assigned_type,
                "execution_mode": task.execution_mode,
                "source_location_id": task.source_location_id,
                "destination_location_id": task.destination_location_id,
                "sku_id": task.sku_id,
                "quantity": task.quantity,
                "lpn": task.lpn,
                "reference_type": task.reference_type,
                "reference_id": task.reference_id,
            },
            "dispatch_block": {
                "external_wcs_call": False,
                "note": "Task factory only creates an internal WMS task. Dispatch remains a separate explicit step.",
            },
            "next_action": "run_wcs_dispatch_preview_when_ready",
        }

    async def dispatch_task(self, task_id: str, callback_url: str | None = None) -> dict:
        task, warehouse, source, destination = await self._load_task_context(task_id)
        existing = await self.db.scalar(
            select(WcsTaskBinding).where(
                WcsTaskBinding.tenant_id == self.tenant_id,
                WcsTaskBinding.task_id == task_id,
            )
        )
        if existing and existing.wcs_task_id:
            return {
                "success": True,
                "already_dispatched": True,
                "binding_id": existing.id,
                "wcs_task_id": existing.wcs_task_id,
                "request_payload": existing.request_payload,
            }

        gate = self.validate_dispatch_gate(task, warehouse, source, destination)
        if not gate["ok"]:
            raise WcsAdapterError("; ".join(gate["issues"]), detail={"message": "WCS dispatch gate failed", "gate": gate})

        payload = self.build_transport_payload(
            task=task,
            warehouse=warehouse,
            source=source,
            destination=destination,
            callback_url=callback_url,
        )
        binding = existing or WcsTaskBinding(
            tenant_id=self.tenant_id,
            task_id=task.id,
            warehouse_id=warehouse.id,
            start_pos=payload["startPos"],
            end_pos=payload["endPos"],
            task_type=payload.get("wtaskinfoType"),
            task_psn=payload.get("wtaskinfoPsn"),
            status=WcsTaskBindingStatus.CREATED.value,
        )
        binding.request_payload = payload
        self.db.add(binding)
        # Durable intent record (outbox-style): commit BEFORE the external call so a
        # WCS task can never exist without a binding row on our side. Without this,
        # a failure after the HTTP call would roll the binding back and orphan the
        # remote task. This commit is a deliberate durability boundary — the one
        # sanctioned exception to "services never commit".
        await self.db.commit()

        config = self._wcs_config(warehouse)
        try:
            response_payload = await self._post_transport_task(config, payload)
        except Exception as exc:
            binding.status = WcsTaskBindingStatus.FAILED.value
            binding.response_payload = {"error": str(exc)[:2000]}
            await self.db.commit()
            raise

        data = response_payload.get("data") if isinstance(response_payload, dict) else {}
        binding.response_payload = response_payload
        binding.wcs_task_id = str(data.get("wtaskinfoTid") or response_payload.get("wtaskinfoTid") or "")
        binding.task_psn = str(data.get("wtaskinfoPsn") or payload.get("wtaskinfoPsn") or "")
        binding.status = WcsTaskBindingStatus.QUEUED.value
        task.assigned_type = AssignedType.AGV.value
        task.assigned_to = task.assigned_to or "agv:wcs"
        task.status = TaskStatus.ASSIGNED.value
        task.assigned_at = task.assigned_at or datetime.now(UTC)
        # Persist the WCS response + task assignment immediately: the remote task now
        # exists, so this state must survive any later failure in the same request.
        await self.db.commit()
        return {
            "success": True,
            "binding_id": binding.id,
            "task_id": task.id,
            "wcs_task_id": binding.wcs_task_id,
            "task_psn": binding.task_psn,
            "request_payload": payload,
            "response_payload": response_payload,
        }

    async def list_point_mappings(
        self,
        warehouse: Warehouse,
        *,
        include_unmapped: bool = False,
    ) -> dict:
        """Return one canonical WCS mapping row per WMS location."""
        locations = await self._warehouse_locations(warehouse.id)
        mappings = self._canonical_point_mappings(warehouse)
        items = []
        mapped_count = 0
        location_keys: set[str] = set()
        for location in locations:
            location_keys.add(location.id)
            location_keys.add(location.barcode)
            mapping = mappings.get(location.id) or mappings.get(location.barcode) or {}
            is_mapped = bool(mapping.get("point_code"))
            if is_mapped:
                mapped_count += 1
            if not include_unmapped and not is_mapped:
                continue
            items.append(self._point_mapping_export_row(location, mapping))
        for key, mapping in mappings.items():
            if key in location_keys or mapping.get("location_id") in location_keys:
                continue
            if not mapping.get("point_code"):
                continue
            items.append(
                {
                    "location_id": mapping.get("location_id"),
                    "location_barcode": mapping.get("location_barcode") or key,
                    "location_type": mapping.get("point_type") or mapping.get("point_role") or "external",
                    "aisle": None,
                    "rack": None,
                    "level": None,
                    "position": None,
                    "wms_agv_accessible": None,
                    "is_external_point": True,
                    **mapping,
                }
            )
        return {
            "warehouse_id": warehouse.id,
            "mapped_locations": mapped_count,
            "unmapped_locations": max(0, len(locations) - mapped_count),
            "external_points": len([item for item in items if item.get("is_external_point")]),
            "items": items,
        }

    async def validate_point_mappings(
        self,
        warehouse: Warehouse,
        mappings: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Validate WMS location to WCS point-code mappings before dispatch can use them."""
        locations = await self._warehouse_locations(warehouse.id)
        by_id = {location.id: location for location in locations}
        by_barcode = {location.barcode: location for location in locations}
        rows = mappings if mappings is not None else list(self._canonical_point_mappings(warehouse).values())
        issues: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        normalized: list[dict[str, Any]] = []
        seen_locations: dict[str, int] = {}
        seen_points: dict[str, int] = {}

        for index, raw in enumerate(rows, start=1):
            record = self._normalize_point_mapping_record(raw)
            location = None
            if record.get("location_id"):
                location = by_id.get(str(record["location_id"]))
            if not location and record.get("location_barcode"):
                location = by_barcode.get(str(record["location_barcode"]))
            if not location:
                external_role = str(record.get("point_role") or record.get("point_type") or "").lower()
                if external_role not in {"dock", "buffer", "agv_station", "aisle_group", "reference"}:
                    issues.append(
                        {
                            "row": index,
                            "code": "unknown_location",
                            "field": "location_id",
                            "message": "Mapping does not match a location in this warehouse",
                        }
                    )
                elif not record.get("location_barcode"):
                    issues.append(
                        {
                            "row": index,
                            "code": "missing_point_reference",
                            "field": "location_barcode",
                            "message": "External WCS points need a stable barcode or point reference",
                        }
                    )
                normalized.append(record)
            else:
                record["location_id"] = location.id
                record["location_barcode"] = location.barcode
                normalized.append(record)

                previous_location_row = seen_locations.get(location.id)
                if previous_location_row:
                    issues.append(
                        {
                            "row": index,
                            "code": "duplicate_location",
                            "field": "location_id",
                            "message": f"Location is already mapped on row {previous_location_row}",
                        }
                    )
                else:
                    seen_locations[location.id] = index

            point_code = str(record.get("point_code") or "").strip()
            if not point_code:
                issues.append(
                    {
                        "row": index,
                        "code": "missing_point_code",
                        "field": "point_code",
                        "message": "WCS point_code is required",
                    }
                )
            else:
                previous_point_row = seen_points.get(point_code)
                if previous_point_row:
                    issues.append(
                        {
                            "row": index,
                            "code": "duplicate_point_code",
                            "field": "point_code",
                            "message": f"WCS point_code is already used on row {previous_point_row}",
                        }
                    )
                else:
                    seen_points[point_code] = index

            if location and record.get("agv_reachable") and not location.is_agv_accessible:
                warnings.append(
                    {
                        "row": index,
                        "code": "location_not_agv_accessible",
                        "field": "agv_reachable",
                        "message": "Mapping is WCS reachable but the WMS location is not AGV accessible",
                    }
                )

        mapped_location_ids = {
            str(record.get("location_id"))
            for record in normalized
            if record.get("location_id") and record.get("point_code")
        }
        external_point_count = len(
            [
                record
                for record in normalized
                if not record.get("location_id") and record.get("point_code")
            ]
        )
        agv_locations = [location for location in locations if location.is_agv_accessible]
        unmapped_agv_locations = [
            {
                "location_id": location.id,
                "location_barcode": location.barcode,
                "location_type": location.location_type,
            }
            for location in agv_locations
            if location.id not in mapped_location_ids
        ]
        return {
            "ok": not issues,
            "warehouse_id": warehouse.id,
            "summary": {
                "rows": len(rows),
                "mapped_locations": len(mapped_location_ids),
                "warehouse_locations": len(locations),
                "agv_accessible_locations": len(agv_locations),
                "unmapped_agv_accessible_locations": len(unmapped_agv_locations),
                "external_points": external_point_count,
            },
            "issues": issues,
            "warnings": warnings,
            "unmapped_agv_locations": unmapped_agv_locations[:100],
            "normalized_mappings": normalized,
        }

    async def replace_point_mappings(
        self,
        warehouse: Warehouse,
        mappings: list[dict[str, Any]],
        *,
        merge: bool = False,
    ) -> dict:
        """Write validated WCS point-code mappings into warehouse adapter config."""
        validation = await self.validate_point_mappings(warehouse, mappings)
        if not validation["ok"]:
            raise WcsAdapterError({"message": "WCS point mapping validation failed", **validation})

        address = dict(warehouse.address or {})
        wcs = dict(address.get("_wcs") or {})
        existing = self._canonical_point_mappings(warehouse) if merge else {}
        for record in validation["normalized_mappings"]:
            if record.get("location_id"):
                existing[str(record["location_id"])] = record
                await self._sync_location_wcs_metadata(record)
            elif record.get("location_barcode"):
                existing[str(record["location_barcode"])] = record
        wcs["point_mappings"] = self._indexed_point_mappings(existing.values())
        address["_wcs"] = wcs
        warehouse.address = address
        await self.db.flush()
        return {
            "status": "configured",
            "warehouse_id": warehouse.id,
            "mapped_locations": len(existing),
            "validation": validation,
        }

    async def update_ready_config(
        self,
        warehouse_id: str,
        *,
        ready_sign: str,
        api_sign: int | str,
        api_num: int | str,
    ) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        payload = self.build_ready_config_payload(
            ready_sign=ready_sign,
            api_sign=api_sign,
            api_num=api_num,
        )
        config = self._wcs_config(warehouse)
        response_payload = await self._post_wcs(
            config,
            "/task/wlReadyAgvRobot/editReadyConfig",
            payload,
            failure_prefix="WCS ready config update failed",
        )
        return {
            "success": True,
            "warehouse_id": warehouse.id,
            "request_payload": payload,
            "response_payload": response_payload,
        }

    async def preview_ready_config(
        self,
        warehouse_id: str,
        *,
        ready_sign: str,
        api_sign: int | str,
        api_num: int | str,
    ) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        payload = self.build_ready_config_payload(
            ready_sign=ready_sign,
            api_sign=api_sign,
            api_num=api_num,
        )
        return {
            "ok": True,
            "dry_run": True,
            "writes": False,
            "action": "wcs.ready_config.preview",
            "risk": "medium",
            "warehouse_id": warehouse.id,
            "planned_request": {
                "method": "POST",
                "endpoint": "/task/wlReadyAgvRobot/editReadyConfig",
                "body": payload,
                "wcs_config": self._redacted_wcs_config(self._wcs_config(warehouse)),
            },
            "next_action": "review_payload_then_request_operator_approval_before_live_wcs_call",
        }

    def build_ready_config_payload(
        self,
        *,
        ready_sign: str,
        api_sign: int | str,
        api_num: int | str,
    ) -> dict:
        if str(api_sign) not in {"-1", "0", "1"}:
            raise WcsAdapterError("WCS ready api_sign must be -1, 0, or 1")
        try:
            normalized_num = int(api_num)
        except (TypeError, ValueError) as exc:
            raise WcsAdapterError("WCS ready api_num must be an integer") from exc
        if normalized_num < 0:
            raise WcsAdapterError("WCS ready api_num cannot be negative")
        return {
            "wrarSign": str(ready_sign),
            "wrarApiSign": str(api_sign),
            "wrarApiNum": str(normalized_num),
        }

    async def complete_quality(
        self,
        warehouse_id: str,
        *,
        wtaskstep_tid: str | None = None,
        wtaskinfo_psn: str | None = None,
        quality_status: str | None = None,
        unqualified_buffer: str | None = None,
        params: str | dict | None = None,
    ) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        payload = self.build_quality_complete_payload(
            wtaskstep_tid=wtaskstep_tid,
            wtaskinfo_psn=wtaskinfo_psn,
            quality_status=quality_status,
            unqualified_buffer=unqualified_buffer,
            params=params,
        )
        config = self._wcs_config(warehouse)
        response_payload = await self._post_wcs(
            config,
            "/QualityComplete",
            payload,
            failure_prefix="WCS quality completion failed",
        )
        return {
            "success": True,
            "warehouse_id": warehouse.id,
            "request_payload": payload,
            "response_payload": response_payload,
        }

    async def preview_quality_complete(
        self,
        warehouse_id: str,
        *,
        wtaskstep_tid: str | None = None,
        wtaskinfo_psn: str | None = None,
        quality_status: str | None = None,
        unqualified_buffer: str | None = None,
        params: str | dict | None = None,
    ) -> dict:
        warehouse = await self._load_warehouse(warehouse_id)
        payload = self.build_quality_complete_payload(
            wtaskstep_tid=wtaskstep_tid,
            wtaskinfo_psn=wtaskinfo_psn,
            quality_status=quality_status,
            unqualified_buffer=unqualified_buffer,
            params=params,
        )
        return {
            "ok": True,
            "dry_run": True,
            "writes": False,
            "action": "wcs.quality_complete.preview",
            "risk": "medium",
            "warehouse_id": warehouse.id,
            "planned_request": {
                "method": "POST",
                "endpoint": "/QualityComplete",
                "body": payload,
                "wcs_config": self._redacted_wcs_config(self._wcs_config(warehouse)),
            },
            "next_action": "review_quality_result_and_buffers_before_live_wcs_call",
        }

    def build_quality_complete_payload(
        self,
        *,
        wtaskstep_tid: str | None = None,
        wtaskinfo_psn: str | None = None,
        quality_status: str | None = None,
        unqualified_buffer: str | None = None,
        params: str | dict | None = None,
    ) -> dict:
        if not wtaskstep_tid and not wtaskinfo_psn:
            raise WcsAdapterError("WCS quality completion requires wtaskstep_tid or wtaskinfo_psn")
        payload: dict[str, Any] = {}
        if wtaskstep_tid:
            payload["wtaskstepTid"] = str(wtaskstep_tid)
        if wtaskinfo_psn:
            payload["wtaskinfoPsn"] = str(wtaskinfo_psn)
        if quality_status:
            payload["qualityStatus"] = str(quality_status)
        if unqualified_buffer:
            payload["unqualifiedBuffer"] = str(unqualified_buffer)
        if params is not None:
            payload["params"] = params
        return payload

    def build_transport_payload(
        self,
        *,
        task: Task,
        warehouse: Warehouse,
        source: Location,
        destination: Location,
        callback_url: str | None,
    ) -> dict:
        task_psn = task.lpn or task.handling_unit_id or task.reference_id or task.id
        config = self._wcs_config(warehouse)
        outparam = {
            "wms_task_id": task.id,
            "reference_type": task.reference_type,
            "reference_id": task.reference_id,
            "source_location_id": task.source_location_id,
            "destination_location_id": task.destination_location_id,
            "source_wcs": self._wcs_point_mapping(warehouse, source),
            "destination_wcs": self._wcs_point_mapping(warehouse, destination),
        }
        return {
            "wtaskinfoType": config.get("task_type_map", {}).get(task.task_type, "AGV搬运"),
            "startPos": self._wcs_point_code(warehouse, source),
            "endPos": self._wcs_point_code(warehouse, destination),
            "wtaskinfoOrder": str(self._wcs_priority(task.priority)),
            "wtaskinfoPsn": task_psn,
            "wtaskinfoReturnurl": callback_url or config.get("callback_url"),
            "wtaskinfoTable": "tasks",
            "wtaskinfoTabletid": task.id,
            "wtaskinfoPalletSpec": self._pallet_spec(warehouse, task),
            "wtaskinfoScode": config.get("scode") or warehouse.code,
            "wtaskinfoOutparam": outparam,
        }

    def validate_dispatch_gate(
        self,
        task: Task,
        warehouse: Warehouse,
        source: Location,
        destination: Location,
    ) -> dict:
        config = self._wcs_config(warehouse)
        issues: list[str] = []
        issue_details: list[dict[str, Any]] = []

        def add_issue(
            *,
            code: str,
            message: str,
            recovery_actions: list[dict[str, str]],
            severity: str = "blocker",
            field: str | None = None,
            location: Location | None = None,
            location_role: str | None = None,
        ) -> None:
            issues.append(message)
            detail: dict[str, Any] = {
                "code": code,
                "severity": severity,
                "message": message,
                "recovery_actions": recovery_actions,
            }
            if field:
                detail["field"] = field
            if location:
                detail["location_role"] = location_role
                detail["location"] = self._dispatch_gate_location_summary(warehouse, location)
            issue_details.append(detail)

        if not config.get("base_url"):
            add_issue(
                code="missing_wcs_base_url",
                field="base_url",
                message="WCS base_url is not configured",
                recovery_actions=[
                    {
                        "action": "configure_wcs_connection",
                        "label": "Configure WCS base_url for this warehouse",
                    }
                ],
            )
        if not (config.get("access_token") or (config.get("username") and config.get("password"))):
            add_issue(
                code="missing_wcs_credentials",
                field="access_token",
                message="WCS token or username/password is not configured",
                recovery_actions=[
                    {
                        "action": "configure_wcs_credentials",
                        "label": "Add a WCS access token or username/password",
                    }
                ],
            )
        if not config.get("callback_url"):
            add_issue(
                code="missing_wcs_callback_url",
                field="callback_url",
                message="WCS callback_url is not configured",
                recovery_actions=[
                    {
                        "action": "configure_wcs_callback",
                        "label": "Configure the WCS task-finish callback URL",
                    }
                ],
            )
        for label, location in (("source", source), ("destination", destination)):
            mapping = self._wcs_point_mapping(warehouse, location)
            if not mapping.get("point_code"):
                add_issue(
                    code=f"missing_{label}_point_code",
                    field="point_code",
                    location=location,
                    location_role=label,
                    message=f"{label} location {location.barcode} has no WCS point_code mapping",
                    recovery_actions=[
                        {
                            "action": "map_wcs_point_code",
                            "label": f"Map {label} location {location.barcode} to a WCS point_code",
                        }
                    ],
                )
            if not mapping.get("agv_reachable"):
                add_issue(
                    code=f"{label}_point_not_wcs_agv_reachable",
                    field="agv_reachable",
                    location=location,
                    location_role=label,
                    message=f"{label} location {location.barcode} is not marked WCS AGV reachable",
                    recovery_actions=[
                        {
                            "action": "mark_wcs_point_agv_reachable",
                            "label": f"Set agv_reachable=true after WCS confirms {location.barcode} is reachable",
                        }
                    ],
                )
            if not location.is_agv_accessible and not self._dispatch_gate_allows_wms_agv_bypass(location, mapping):
                add_issue(
                    code=f"{label}_location_not_wms_agv_accessible",
                    field="is_agv_accessible",
                    location=location,
                    location_role=label,
                    message=f"{label} location {location.barcode} is not AGV accessible",
                    recovery_actions=[
                        {
                            "action": "mark_wms_location_agv_accessible",
                            "label": f"Mark {location.barcode} AGV accessible or choose an AGV-accessible location",
                        }
                    ],
                )
        if (
            task.task_type in {"putaway", "move", "replenish"}
            and self._dispatch_gate_point_type(warehouse, destination) == LocationType.DOCK.value
        ):
            add_issue(
                code="dock_destination_not_storage",
                field="destination_location_id",
                location=destination,
                location_role="destination",
                message="Dock doors cannot be WCS storage destinations",
                recovery_actions=[
                    {
                        "action": "choose_storage_destination",
                        "label": "Choose a storage, buffer, or AGV station destination instead of a dock door",
                    },
                    {
                        "action": "change_task_type",
                        "label": "Use a dock-oriented task type when the destination is intentionally a dock door",
                    },
                ],
            )
        return {
            "ok": not issues,
            "issues": issues,
            "issue_details": issue_details,
            "recovery_actions": self._dispatch_gate_recovery_actions(issue_details),
            "source": self._dispatch_gate_location_summary(warehouse, source),
            "destination": self._dispatch_gate_location_summary(warehouse, destination),
            "source_point": self._wcs_point_mapping(warehouse, source).get("point_code"),
            "destination_point": self._wcs_point_mapping(warehouse, destination).get("point_code"),
        }

    def _dispatch_gate_location_summary(self, warehouse: Warehouse, location: Location) -> dict[str, Any]:
        mapping = self._wcs_point_mapping(warehouse, location)
        return {
            "location_id": location.id,
            "barcode": location.barcode,
            "location_type": location.location_type,
            "point_code": mapping.get("point_code"),
            "point_type": self._dispatch_gate_point_type(warehouse, location),
            "point_role": mapping.get("point_role") or mapping.get("point_type") or location.location_type,
            "agv_reachable": bool(mapping.get("agv_reachable")),
            "wms_agv_accessible": bool(location.is_agv_accessible),
        }

    def _dispatch_gate_point_type(self, warehouse: Warehouse, location: Location) -> str:
        mapping = self._wcs_point_mapping(warehouse, location)
        point_type = str(mapping.get("point_type") or mapping.get("point_role") or location.location_type or "").strip()
        point_type = point_type.lower()
        if point_type in {
            LocationType.STORAGE.value,
            LocationType.DOCK.value,
            LocationType.BUFFER.value,
            LocationType.AGV_STATION.value,
        }:
            return point_type
        return location.location_type

    def _dispatch_gate_allows_wms_agv_bypass(self, location: Location, mapping: dict[str, Any]) -> bool:
        point_type = str(mapping.get("point_type") or mapping.get("point_role") or location.location_type or "").lower()
        return point_type in {
            LocationType.DOCK.value,
            LocationType.BUFFER.value,
            LocationType.AGV_STATION.value,
        }

    def _dispatch_gate_recovery_actions(self, issue_details: list[dict[str, Any]]) -> list[dict[str, str]]:
        actions: list[dict[str, str]] = []
        seen: set[str] = set()
        for issue in issue_details:
            for action in issue.get("recovery_actions") or []:
                action_key = str(action.get("action") or action.get("label") or "")
                if action_key and action_key not in seen:
                    seen.add(action_key)
                    actions.append(action)
        return actions

    async def apply_task_callback(self, payload: dict[str, Any]) -> dict:
        binding = await self._find_binding_for_callback(payload)
        if not binding:
            raise WcsAdapterError("No WCS task binding matches callback")

        step_status = self._int_or_none(payload.get("stepStatus"))
        mapped_status = WCS_STATUS_MAP.get(step_status, binding.status)
        binding.wcs_step_id = str(payload.get("stepTid") or binding.wcs_step_id or "")
        binding.task_psn = str(payload.get("taskPsn") or binding.task_psn or "")
        binding.agv_unit_id = str(payload.get("stepAgvIp") or payload.get("stepExecutename") or "wcs")
        binding.last_step_status = step_status
        binding.last_step_status_name = payload.get("stepStatusName")
        binding.last_callback_at = datetime.now(UTC)
        binding.last_callback_payload = payload
        binding.status = mapped_status

        task = await self.db.scalar(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == binding.task_id)
        )
        if not task:
            raise WcsAdapterError("Bound WMS task no longer exists")
        task.assigned_type = AssignedType.AGV.value
        task.assigned_to = f"agv:{binding.agv_unit_id or 'wcs'}"

        if mapped_status in (WcsTaskBindingStatus.ASSIGNED.value, WcsTaskBindingStatus.QUEUED.value):
            task.status = TaskStatus.ASSIGNED.value
            task.assigned_at = task.assigned_at or datetime.now(UTC)
        elif mapped_status == WcsTaskBindingStatus.IN_PROGRESS.value:
            task.status = TaskStatus.IN_PROGRESS.value
            task.started_at = task.started_at or datetime.now(UTC)
        elif mapped_status == WcsTaskBindingStatus.PAUSED.value:
            task.status = TaskStatus.IN_PROGRESS.value
            task.failure_reason = payload.get("stepNote") or "WCS task paused"
        elif mapped_status == WcsTaskBindingStatus.CANCELLED.value:
            task.status = TaskStatus.CANCELLED.value
            task.failure_reason = payload.get("stepNote") or "WCS task cancelled"
        elif mapped_status == WcsTaskBindingStatus.FAILED.value:
            await AGVService(self.db, self.tenant_id).fail_task(
                task.id,
                binding.agv_unit_id or "wcs",
                payload.get("stepNote") or payload.get("stepStatusName") or "WCS task failed",
            )
            binding.failure_reason = task.failure_reason
        elif mapped_status == WcsTaskBindingStatus.COMPLETED.value:
            if task.status != TaskStatus.COMPLETED.value:
                await AGVService(self.db, self.tenant_id).complete_task(
                    task.id,
                    binding.agv_unit_id or "wcs",
                    task.quantity,
                )
            binding.completed_at = task.completed_at or datetime.now(UTC)

        await self.db.flush()
        return {
            "code": 0,
            "binding_id": binding.id,
            "task_id": binding.task_id,
            "status": binding.status,
            "step_status": step_status,
        }

    async def preview_task_callback(self, payload: dict[str, Any]) -> dict:
        binding = await self._find_binding_for_callback(payload)
        if not binding:
            raise WcsAdapterError("No WCS task binding matches callback")
        task = await self.db.scalar(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == binding.task_id)
        )
        step_status = self._int_or_none(payload.get("stepStatus"))
        mapped_status = WCS_STATUS_MAP.get(step_status, binding.status)
        task_status_after = task.status if task else None
        if mapped_status in (WcsTaskBindingStatus.ASSIGNED.value, WcsTaskBindingStatus.QUEUED.value):
            task_status_after = TaskStatus.ASSIGNED.value
        elif mapped_status in (
            WcsTaskBindingStatus.IN_PROGRESS.value,
            WcsTaskBindingStatus.PAUSED.value,
        ):
            task_status_after = TaskStatus.IN_PROGRESS.value
        elif mapped_status == WcsTaskBindingStatus.CANCELLED.value:
            task_status_after = TaskStatus.CANCELLED.value
        elif mapped_status == WcsTaskBindingStatus.FAILED.value:
            task_status_after = TaskStatus.FAILED.value
        elif mapped_status == WcsTaskBindingStatus.COMPLETED.value:
            task_status_after = TaskStatus.COMPLETED.value
        return {
            "ok": True,
            "dry_run": True,
            "action": "wcs.callback_replay",
            "matched_binding": self._binding_summary(binding),
            "step_status": step_status,
            "mapped_wcs_status": mapped_status,
            "task_status_before": task.status if task else None,
            "task_status_after": task_status_after,
            "would_create_inventory_movement": (
                mapped_status == WcsTaskBindingStatus.COMPLETED.value
                and bool(task)
                and task.status != TaskStatus.COMPLETED.value
            ),
            "planned_request": {
                "endpoint": "POST /api/v1/integrations/wcs/webhook/{tenant_id}/taskfinish",
                "body": payload,
                "mutates_state": False,
            },
            "confirmation_required_for_write": False,
            "next_action": "review_replay_before_live_webhook_or_simulator_callback",
        }

    async def _load_task_context(self, task_id: str) -> tuple[Task, Warehouse, Location, Location]:
        task = await self.db.scalar(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        if not task:
            raise WcsAdapterError("Task not found")
        warehouse = await self.db.scalar(
            select(Warehouse).where(
                Warehouse.tenant_id == self.tenant_id,
                Warehouse.id == task.warehouse_id,
            )
        )
        if not warehouse:
            raise WcsAdapterError("Warehouse not found")
        if not task.source_location_id or not task.destination_location_id:
            raise WcsAdapterError("WCS transport requires source and destination locations")
        source = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.id == task.source_location_id,
            )
        )
        destination = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.id == task.destination_location_id,
            )
        )
        if not source or not destination:
            raise WcsAdapterError("WCS transport locations are not valid")
        return task, warehouse, source, destination

    async def _load_warehouse(self, warehouse_id: str) -> Warehouse:
        warehouse = await self.db.scalar(
            select(Warehouse).where(
                Warehouse.tenant_id == self.tenant_id,
                Warehouse.id == warehouse_id,
            )
        )
        if not warehouse:
            raise WcsAdapterError("Warehouse not found")
        return warehouse

    async def _build_certification_task_plan(
        self,
        *,
        warehouse_id: str,
        source_location_id: str,
        destination_location_id: str,
        sku_id: str,
        quantity: int,
        certification_scope: str,
        reference_id: str | None,
        lpn_prefix: str | None,
    ) -> dict[str, Any]:
        normalized_scope = str(
            certification_scope or self.WCS_CERTIFICATION_DEFAULT_SCOPE
        ).strip()
        if normalized_scope not in self.WCS_CERTIFICATION_ALLOWED_SCOPES:
            raise WcsAdapterError(
                {
                    "code": "invalid_certification_scope",
                    "message": "Only sandbox certification scopes are allowed for this task factory.",
                    "allowed_scopes": sorted(self.WCS_CERTIFICATION_ALLOWED_SCOPES),
                }
            )

        if int(quantity) <= 0:
            raise WcsAdapterError(
                {
                    "code": "invalid_quantity",
                    "message": "Certification task quantity must be greater than zero.",
                }
            )
        if reference_id and len(str(reference_id)) > 36:
            raise WcsAdapterError(
                {
                    "code": "reference_id_too_long",
                    "message": "reference_id must be 36 characters or fewer.",
                }
            )

        warehouse = await self._load_warehouse(warehouse_id)
        source = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse.id,
                Location.id == source_location_id,
            )
        )
        destination = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse.id,
                Location.id == destination_location_id,
            )
        )
        if not source or not destination:
            raise WcsAdapterError(
                {
                    "code": "invalid_certification_locations",
                    "message": "Source and destination locations must both exist in the same tenant warehouse.",
                }
            )
        if source.id == destination.id:
            raise WcsAdapterError(
                {
                    "code": "same_source_destination",
                    "message": "Source and destination must be different locations for certification transport.",
                }
            )

        sku = await self.db.scalar(
            select(SKU).where(
                SKU.tenant_id == self.tenant_id,
                SKU.id == sku_id,
            )
        )
        if not sku:
            raise WcsAdapterError(
                {
                    "code": "sku_not_found",
                    "message": "SKU not found for the current tenant.",
                }
            )

        task_reference_id = str(reference_id or uuid4())
        lpn = self._certification_lpn(lpn_prefix)
        task_fields = {
            "tenant_id": self.tenant_id,
            "warehouse_id": warehouse.id,
            "task_type": TaskType.MOVE.value,
            "status": TaskStatus.PENDING.value,
            "priority": 5,
            "sku_id": sku.id,
            "quantity": int(quantity),
            "lpn": lpn,
            "execution_mode": AssignedType.AGV.value,
            "source_location_id": source.id,
            "destination_location_id": destination.id,
            "assigned_type": AssignedType.UNASSIGNED.value,
            "reference_type": self.WCS_CERTIFICATION_REFERENCE_TYPE,
            "reference_id": task_reference_id,
        }
        return {
            "warehouse": warehouse,
            "source": source,
            "destination": destination,
            "sku": sku,
            "task_fields": task_fields,
            "certification_scope": normalized_scope,
            "lpn_prefix": str(lpn_prefix or self.WCS_CERTIFICATION_DEFAULT_LPN_PREFIX),
        }

    def _certification_lpn(self, lpn_prefix: str | None) -> str:
        raw_prefix = (
            str(lpn_prefix or self.WCS_CERTIFICATION_DEFAULT_LPN_PREFIX).strip()
            or self.WCS_CERTIFICATION_DEFAULT_LPN_PREFIX
        )
        safe_prefix = "-".join(part for part in raw_prefix.split() if part)
        suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        trace = uuid4().hex[:6].upper()
        lpn = f"{safe_prefix}-{suffix}-{trace}"
        return lpn[:50]

    async def _find_binding_for_callback(self, payload: dict[str, Any]) -> WcsTaskBinding | None:
        task_tid = str(payload.get("taskTid") or "")
        task_psn = str(payload.get("taskPsn") or payload.get("wtaskinfoPsn") or "")
        step_tid = str(payload.get("stepTid") or "")
        conditions = []
        if task_tid:
            conditions.append(WcsTaskBinding.wcs_task_id == task_tid)
        if task_psn:
            conditions.append(WcsTaskBinding.task_psn == task_psn)
        if step_tid:
            conditions.append(WcsTaskBinding.wcs_step_id == step_tid)
        if not conditions:
            return None
        return await self.db.scalar(
            select(WcsTaskBinding)
            .where(WcsTaskBinding.tenant_id == self.tenant_id)
            .where(or_(*conditions))
            .order_by(WcsTaskBinding.created_at.desc())
        )

    async def _post_transport_task(self, config: dict, payload: dict) -> dict:
        return await self._post_wcs(
            config,
            "/task/wlTaskInfo/addTransportTask",
            payload,
            failure_prefix="WCS task creation failed",
        )

    async def _post_wcs(
        self,
        config: dict,
        path: str,
        payload: dict,
        *,
        failure_prefix: str,
    ) -> dict:
        base_url = str(config.get("base_url") or "").rstrip("/")
        if not base_url:
            raise WcsAdapterError("WCS base_url is not configured")
        token = config.get("access_token") or await self._login_token(config)
        if not token:
            raise WcsAdapterError("WCS token or username/password is not configured")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{base_url}{path}",
                json=payload,
                headers={"Content-Type": "application/json", "token": str(token or "")},
            )
        try:
            body = response.json()
        except ValueError:
            body = {"raw": response.text}
        if response.status_code >= 400 or body.get("success") in (False, "false", "False"):
            raise WcsAdapterError(f"{failure_prefix}: {body.get('msg') or body}")
        return body

    async def _login_token(self, config: dict) -> str | None:
        base_url = str(config.get("base_url") or "").rstrip("/")
        username = config.get("username")
        password = config.get("password")
        if not base_url or not username or not password:
            return None
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{base_url}/loginToken",
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
            )
        body = response.json()
        return body.get("token") or body.get("access_token") or body.get("data")

    async def _sync_location_wcs_metadata(self, record: dict[str, Any]) -> None:
        location_id = record.get("location_id")
        if not location_id:
            return
        location = await self.db.scalar(
            select(Location).where(
                Location.tenant_id == self.tenant_id,
                Location.id == str(location_id),
            )
        )
        if not location:
            return
        existing = location.wcs_point_metadata if isinstance(location.wcs_point_metadata, dict) else {}
        location.wcs_point_metadata = {
            **existing,
            **record,
            "source": record.get("source") or existing.get("source") or "wcs_point_mapping",
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def _wcs_config(self, warehouse: Warehouse) -> dict:
        return ((warehouse.address or {}).get("_wcs") or {}).copy()

    def _merge_config_update(
        self,
        warehouse: Warehouse,
        existing: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        proposed = dict(existing or {})
        proposed["point_mappings"] = existing.get("point_mappings") or {}
        for key in (
            "base_url",
            "callback_url",
            "username",
            "password",
            "access_token",
            "scode",
            "default_pallet_spec",
            "task_type_map",
        ):
            if key not in changes:
                continue
            value = changes[key]
            if isinstance(value, str):
                value = value.strip()
            if key == "base_url" and value:
                value = str(value).rstrip("/")
            proposed[key] = value
        if not proposed.get("scode"):
            proposed["scode"] = warehouse.code
        if not isinstance(proposed.get("task_type_map"), dict):
            proposed["task_type_map"] = {}
        return proposed

    def _validate_config_update(self, config: dict[str, Any]) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []
        base_url = str(config.get("base_url") or "").strip()
        callback_url = str(config.get("callback_url") or "").strip()

        if not base_url:
            issues.append(
                {
                    "code": "missing_wcs_base_url",
                    "field": "base_url",
                    "message": "WCS base_url is required before live sandbox calls.",
                }
            )
        else:
            parsed = urlparse(base_url)
            if parsed.scheme != "https":
                issues.append(
                    {
                        "code": "wcs_base_url_must_be_https",
                        "field": "base_url",
                        "message": "WCS base_url must use https for sandbox certification.",
                    }
                )
            if self._looks_like_private_wcs_host(parsed.hostname or ""):
                issues.append(
                    {
                        "code": "wcs_base_url_private_host",
                        "field": "base_url",
                        "message": "WCS base_url must not target localhost or a private network host.",
                    }
                )

        if callback_url:
            parsed_callback = urlparse(callback_url)
            if parsed_callback.scheme != "https":
                warnings.append(
                    {
                        "code": "wcs_callback_url_not_https",
                        "field": "callback_url",
                        "message": "WCS callback_url should be https for external sandbox certification.",
                    }
                )
        else:
            warnings.append(
                {
                    "code": "missing_wcs_callback_url",
                    "field": "callback_url",
                    "message": "WCS dispatch completion callbacks require a callback_url.",
                }
            )

        if not (config.get("access_token") or (config.get("username") and config.get("password"))):
            issues.append(
                {
                    "code": "missing_wcs_credentials",
                    "field": "access_token",
                    "message": "WCS access_token or username/password is required.",
                }
            )

        return {"ok": not issues, "issues": issues, "warnings": warnings}

    def _changed_config_keys(self, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
        keys = sorted(set(before.keys()) | set(after.keys()))
        changed = []
        for key in keys:
            if key == "point_mappings":
                continue
            before_value = before.get(key)
            after_value = after.get(key)
            if key == "task_type_map" and not before_value and after_value == {}:
                continue
            if before_value != after_value:
                changed.append(key)
        return changed

    def _looks_like_private_wcs_host(self, hostname: str) -> bool:
        normalized = hostname.strip().lower()
        if normalized in {"localhost", "127.0.0.1", "::1"}:
            return True
        try:
            parsed = ip_address(normalized.strip("[]"))
        except ValueError:
            return False
        return parsed.is_private or parsed.is_loopback or parsed.is_link_local

    async def _warehouse_locations(self, warehouse_id: str) -> list[Location]:
        result = await self.db.scalars(
            select(Location)
            .where(
                Location.tenant_id == self.tenant_id,
                Location.warehouse_id == warehouse_id,
            )
            .order_by(Location.barcode)
        )
        return list(result.all())

    def _canonical_point_mappings(self, warehouse: Warehouse) -> dict[str, dict[str, Any]]:
        mappings = self._wcs_config(warehouse).get("point_mappings") or {}
        if not isinstance(mappings, dict):
            return {}
        canonical: dict[str, dict[str, Any]] = {}
        for value in mappings.values():
            if not isinstance(value, dict):
                continue
            record = self._normalize_point_mapping_record(value)
            key = str(record.get("location_id") or record.get("location_barcode") or "")
            if key:
                canonical[key] = record
        return canonical

    def _indexed_point_mappings(self, records: list[dict[str, Any]] | Any) -> dict[str, dict[str, Any]]:
        indexed: dict[str, dict[str, Any]] = {}
        for raw in records:
            record = self._normalize_point_mapping_record(raw)
            if record.get("location_id"):
                indexed[str(record["location_id"])] = record
            if record.get("location_barcode"):
                indexed[str(record["location_barcode"])] = record
        return indexed

    def _normalize_point_mapping_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        def clean(value: Any) -> str | None:
            text = str(value or "").strip()
            return text or None

        point_type = clean(raw.get("point_type") or raw.get("point_role"))
        return {
            "location_id": clean(raw.get("location_id")),
            "location_barcode": clean(raw.get("location_barcode") or raw.get("barcode")),
            "point_code": clean(raw.get("point_code") or raw.get("wcs_point_code")),
            "point_type": point_type,
            "point_role": clean(raw.get("point_role") or point_type),
            "point_name": clean(raw.get("point_name")),
            "buffer_code": clean(raw.get("buffer_code")),
            "aisle_group": clean(raw.get("aisle_group")),
            "station_role": clean(raw.get("station_role")),
            "agv_reachable": self._bool_value(raw.get("agv_reachable"), True),
            "wcs_metadata": raw.get("wcs_metadata") if isinstance(raw.get("wcs_metadata"), dict) else None,
        }

    def _point_mapping_export_row(self, location: Location, mapping: dict[str, Any]) -> dict[str, Any]:
        metadata = location.wcs_point_metadata if isinstance(location.wcs_point_metadata, dict) else {}
        return {
            "location_id": location.id,
            "location_barcode": location.barcode,
            "location_type": location.location_type,
            "aisle": location.aisle,
            "rack": location.rack,
            "level": location.level,
            "position": location.position,
            "wms_agv_accessible": location.is_agv_accessible,
            "point_code": mapping.get("point_code") or metadata.get("point_code"),
            "point_type": mapping.get("point_type") or metadata.get("point_type"),
            "point_role": mapping.get("point_role") or metadata.get("point_role"),
            "point_name": mapping.get("point_name") or metadata.get("point_name"),
            "buffer_code": mapping.get("buffer_code") or metadata.get("buffer_code"),
            "aisle_group": mapping.get("aisle_group") or metadata.get("aisle_group"),
            "station_role": mapping.get("station_role") or metadata.get("station_role"),
            "agv_reachable": mapping.get("agv_reachable", metadata.get("agv_reachable", True)),
            "wcs_metadata": mapping.get("wcs_metadata") or metadata.get("wcs_metadata"),
            "dimensions": location.dimensions or metadata.get("dimensions") or {},
            "layout_metadata": location.layout_metadata or {},
        }

    def _wcs_point_mapping(self, warehouse: Warehouse, location: Location) -> dict:
        mappings = self._wcs_config(warehouse).get("point_mappings") or {}
        if not isinstance(mappings, dict):
            mappings = {}
        value = mappings.get(location.id) or mappings.get(location.barcode) or {}
        mapping = value if isinstance(value, dict) else {}
        metadata = location.wcs_point_metadata if isinstance(location.wcs_point_metadata, dict) else {}
        return {**metadata, **mapping} if metadata or mapping else {}

    def _wcs_point_code(self, warehouse: Warehouse, location: Location) -> str:
        mapping = self._wcs_point_mapping(warehouse, location)
        return str(mapping.get("point_code") or location.barcode)

    def _pallet_spec(self, warehouse: Warehouse, task: Task) -> str | None:
        config = self._wcs_config(warehouse)
        return config.get("default_pallet_spec") or ("GMA" if task.handling_unit_id else None)

    def _wcs_priority(self, task_priority: int) -> int:
        return max(1, min(127, int(task_priority or 5)))

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _bool_value(self, value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"0", "false", "no", "n", "off"}
        return bool(value)

    def _redacted_wcs_config(self, config: dict) -> dict:
        redacted = dict(config or {})
        if redacted.get("password"):
            redacted["password"] = "***redacted***"
        if redacted.get("access_token"):
            redacted["access_token"] = "***redacted***"
        return redacted

    def _binding_summary(self, binding: WcsTaskBinding | None) -> dict | None:
        if not binding:
            return None
        return {
            "id": binding.id,
            "task_id": binding.task_id,
            "warehouse_id": binding.warehouse_id,
            "wcs_task_id": binding.wcs_task_id,
            "wcs_step_id": binding.wcs_step_id,
            "task_psn": binding.task_psn,
            "agv_unit_id": binding.agv_unit_id,
            "status": binding.status,
            "start_pos": binding.start_pos,
            "end_pos": binding.end_pos,
            "task_type": binding.task_type,
            "last_step_status": binding.last_step_status,
            "last_step_status_name": binding.last_step_status_name,
            "last_callback_at": binding.last_callback_at.isoformat() if binding.last_callback_at else None,
            "completed_at": binding.completed_at.isoformat() if binding.completed_at else None,
            "failure_reason": binding.failure_reason,
            "request_payload": binding.request_payload,
            "response_payload": binding.response_payload,
            "last_callback_payload": binding.last_callback_payload,
        }


__all__ = ["WCS_STATUS_MAP", "WcsAdapterError", "WcsAdapterService"]
