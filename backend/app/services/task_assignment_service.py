"""
Task Assignment Service — assign warehouse tasks to specific employees.

Supports:
1. Manual assign: supervisor assigns a task to a specific picker
2. Auto-assign: system distributes tasks evenly across available workers
3. Reassign: move task from one worker to another
4. My tasks: worker sees only their assigned tasks
"""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import AssignedType, Task, TaskStatus
from app.models.tenant import User


class TaskAssignmentService:
    def __init__(self, db: AsyncSession, tenant_id: str):
        self.db = db
        self.tenant_id = tenant_id

    async def assign_task(self, task_id: str, user_id: str) -> dict:
        """Manually assign a task to a specific employee."""
        result = await self.db.execute(
            select(Task).where(Task.tenant_id == self.tenant_id, Task.id == task_id)
        )
        task = result.scalar_one()

        if task.status not in (TaskStatus.PENDING.value, TaskStatus.ASSIGNED.value):
            return {"success": False, "error": f"Task is {task.status}, cannot reassign"}

        # Get user name
        user_result = await self.db.execute(
            select(User).where(User.tenant_id == self.tenant_id, User.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            return {"success": False, "error": "User not found"}

        task.assigned_to = user_id
        task.assigned_type = AssignedType.HUMAN.value
        task.status = TaskStatus.ASSIGNED.value
        task.assigned_at = datetime.now(UTC)

        await self.db.flush()
        return {
            "success": True,
            "task_id": task_id,
            "assigned_to": user_id,
            "assigned_name": user.full_name,
        }

    async def auto_assign_tasks(
        self,
        warehouse_id: str,
        user_ids: list[str] | None = None,
        max_tasks_per_worker: int = 10,
    ) -> dict:
        """
        Auto-distribute pending unassigned tasks evenly across workers.
        If user_ids not specified, uses all active operators in the tenant.
        """
        # Get available workers
        if user_ids:
            workers = user_ids
        else:
            result = await self.db.execute(
                select(User.id).where(
                    User.tenant_id == self.tenant_id,
                    User.role == "operator",
                    User.is_active == True,  # noqa
                )
            )
            workers = [row[0] for row in result.all()]

        if not workers:
            return {"success": False, "error": "No available workers"}

        # Get current task counts per worker
        counts: dict[str, int] = {}
        for wid in workers:
            result = await self.db.execute(
                select(func.count(Task.id)).where(
                    Task.tenant_id == self.tenant_id,
                    Task.assigned_to == wid,
                    Task.status.in_([TaskStatus.ASSIGNED.value, TaskStatus.IN_PROGRESS.value]),
                )
            )
            counts[wid] = result.scalar() or 0

        # Get pending unassigned tasks
        result = await self.db.execute(
            select(Task)
            .where(
                Task.tenant_id == self.tenant_id,
                Task.warehouse_id == warehouse_id,
                Task.status == TaskStatus.PENDING.value,
                Task.assigned_type == AssignedType.UNASSIGNED.value,
            )
            .order_by(Task.priority, Task.created_at)
        )
        tasks = list(result.scalars())

        # Batch-fetch worker names
        name_result = await self.db.execute(
            select(User.id, User.full_name).where(
                User.tenant_id == self.tenant_id, User.id.in_(workers)
            )
        )
        worker_names = {row.id: row.full_name for row in name_result.all()}

        assigned_count = 0
        assignments = []

        for task in tasks:
            # Find worker with fewest active tasks
            eligible = {w: c for w, c in counts.items() if c < max_tasks_per_worker}
            if not eligible:
                break

            worker = min(eligible, key=eligible.get)
            task.assigned_to = worker
            task.assigned_type = AssignedType.HUMAN.value
            task.status = TaskStatus.ASSIGNED.value
            task.assigned_at = datetime.now(UTC)
            counts[worker] += 1
            assigned_count += 1

            name = worker_names.get(worker) or worker

            assignments.append(
                {
                    "task_id": task.id,
                    "task_type": task.task_type,
                    "assigned_to": worker,
                    "assigned_name": name,
                }
            )

        await self.db.flush()
        return {
            "success": True,
            "total_assigned": assigned_count,
            "workers_used": len(set(a["assigned_to"] for a in assignments)),
            "assignments": assignments,
        }

    async def get_my_tasks(self, user_id: str) -> list[dict]:
        """Get tasks assigned to a specific worker."""
        query = (
            select(Task)
            .where(
                Task.assigned_to == user_id,
                Task.status.in_([TaskStatus.ASSIGNED.value, TaskStatus.IN_PROGRESS.value]),
            )
            .order_by(Task.priority, Task.created_at)
        )
        # Endpoint is reachable by platform admins (tenant_id=None); only scope
        # when a tenant context exists so admin behavior is preserved.
        if self.tenant_id:
            query = query.where(Task.tenant_id == self.tenant_id)
        result = await self.db.execute(query)
        return [
            {
                "task_id": t.id,
                "type": t.task_type,
                "status": t.status,
                "priority": t.priority,
                "sku_id": t.sku_id,
                "quantity": t.quantity,
                "source_location": t.source_location_id,
                "dest_location": t.destination_location_id,
            }
            for t in result.scalars()
        ]

    async def get_workload_summary(self, warehouse_id: str) -> list[dict]:
        """Get task distribution across all workers (for supervisor view)."""
        result = await self.db.execute(
            select(User.id, User.full_name).where(
                User.tenant_id == self.tenant_id,
                User.role == "operator",
                User.is_active == True,  # noqa
            )
        )
        workers = result.all()

        summary = []
        for wid, name in workers:
            task_counts = await self.db.execute(
                select(Task.status, func.count(Task.id))
                .where(
                    Task.tenant_id == self.tenant_id,
                    Task.assigned_to == wid,
                    Task.warehouse_id == warehouse_id,
                )
                .group_by(Task.status)
            )
            status_map = {row[0]: row[1] for row in task_counts.all()}
            summary.append(
                {
                    "user_id": wid,
                    "name": name,
                    "assigned": status_map.get(TaskStatus.ASSIGNED.value, 0),
                    "in_progress": status_map.get(TaskStatus.IN_PROGRESS.value, 0),
                    "completed_today": status_map.get(TaskStatus.COMPLETED.value, 0),
                    "total_active": status_map.get(TaskStatus.ASSIGNED.value, 0)
                    + status_map.get(TaskStatus.IN_PROGRESS.value, 0),
                }
            )

        summary.sort(key=lambda w: w["total_active"])
        return summary
