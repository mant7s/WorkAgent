"""WorkflowEngine - DAG 工作流引擎

基于轻量级 Agent 框架 v2 设计文档第 4.2 节实现：
- DAG 执行：拓扑排序
- 支持模式：sequential / parallel / dag
- 信号处理：pause / resume / cancel
- 状态管理：PENDING / RUNNING / COMPLETED / FAILED
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Set, Union
from uuid import uuid4

import structlog

logger = structlog.get_logger(__name__)


class TaskStatus(Enum):
    """任务状态"""

    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class WorkflowStatus(Enum):
    """工作流状态"""

    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class WorkflowSignal(Enum):
    """工作流信号"""

    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


@dataclass
class Task:
    """工作流任务

    Attributes:
        id: 任务唯一标识
        name: 任务名称
        func: 任务执行函数
        args: 位置参数
        kwargs: 关键字参数
        dependencies: 依赖任务 ID 列表
        status: 任务状态
        result: 执行结果
        error: 错误信息
        started_at: 开始时间
        completed_at: 完成时间
        timeout: 超时时间（秒）
        retries: 重试次数
        retry_count: 当前重试计数
    """

    id: str
    name: str
    func: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeout: float = 30.0
    retries: int = 0
    retry_count: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())


@dataclass
class Workflow:
    """工作流定义

    Attributes:
        id: 工作流唯一标识
        name: 工作流名称
        tasks: 任务字典
        status: 工作流状态
        created_at: 创建时间
        started_at: 开始时间
        completed_at: 完成时间
        metadata: 元数据
    """

    id: str
    name: str
    tasks: Dict[str, Task] = field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid4())


class WorkflowError(Exception):
    """工作流错误"""

    pass


class WorkflowEngine:
    """轻量级工作流引擎 - Temporal 的替代方案

    特性：
    1. 异步任务执行
    2. DAG 依赖管理
    3. 并行/串行执行
    4. 简单的状态持久化
    5. 超时和重试
    6. 信号处理（暂停/恢复/取消）

    与 Temporal 的区别：
    - 无外部依赖，纯 Python 实现
    - 状态保存在内存，非数据库事务
    - 适合短任务（<30分钟），不支持跨天持久化

    Example:
        >>> engine = WorkflowEngine(max_workers=5)
        >>>
        >>> # 定义任务
        >>> task1 = Task(id="t1", name="fetch_data", func=fetch_func)
        >>> task2 = Task(id="t2", name="process", func=process_func, dependencies=["t1"])
        >>>
        >>> # 执行工作流
        >>> workflow = Workflow(id="wf1", name="data_pipeline", tasks={"t1": task1, "t2": task2})
        >>> results = await engine.execute_workflow(workflow, mode="dag")
    """

    def __init__(
        self,
        max_workers: int = 5,
        state_store: Optional[Any] = None,
    ):
        self.max_workers = max_workers
        self.state_store = state_store
        self.semaphore = asyncio.Semaphore(max_workers)
        self._workflows: Dict[str, Workflow] = {}
        self._signals: Dict[str, WorkflowSignal] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "workflow_engine.initialized",
            max_workers=max_workers,
        )

    async def execute(
        self,
        tasks: List[Task],
        mode: str = "dag",  # "sequential", "parallel", "dag"
        workflow_id: Optional[str] = None,
        workflow_name: str = "unnamed_workflow",
    ) -> Dict[str, Any]:
        """执行工作流

        Args:
            tasks: 任务列表
            mode: 执行模式（sequential/parallel/dag）
            workflow_id: 工作流 ID（可选）
            workflow_name: 工作流名称

        Returns:
            Dict: 任务执行结果
        """
        workflow_id = workflow_id or str(uuid4())
        workflow = Workflow(
            id=workflow_id,
            name=workflow_name,
            tasks={t.id: t for t in tasks},
        )

        return await self.execute_workflow(workflow, mode)

    async def execute_workflow(
        self,
        workflow: Workflow,
        mode: str = "dag",
    ) -> Dict[str, Any]:
        """执行工作流

        Args:
            workflow: 工作流对象
            mode: 执行模式（sequential/parallel/dag）

        Returns:
            Dict: 任务执行结果
        """
        async with self._lock:
            self._workflows[workflow.id] = workflow
            workflow.status = WorkflowStatus.RUNNING
            workflow.started_at = datetime.now()

        logger.info(
            "workflow.started",
            workflow_id=workflow.id,
            name=workflow.name,
            mode=mode,
            task_count=len(workflow.tasks),
        )

        try:
            if mode == "sequential":
                results = await self._execute_sequential(workflow)
            elif mode == "parallel":
                results = await self._execute_parallel(workflow)
            elif mode == "dag":
                results = await self._execute_dag(workflow)
            else:
                raise WorkflowError(f"Unknown execution mode: {mode}")

            async with self._lock:
                workflow.status = WorkflowStatus.COMPLETED
                workflow.completed_at = datetime.now()

            logger.info(
                "workflow.completed",
                workflow_id=workflow.id,
                name=workflow.name,
                duration=(workflow.completed_at - workflow.started_at).total_seconds(),
            )

            return results

        except Exception as e:
            async with self._lock:
                workflow.status = WorkflowStatus.FAILED
                workflow.completed_at = datetime.now()

            logger.error(
                "workflow.failed",
                workflow_id=workflow.id,
                name=workflow.name,
                error=str(e),
            )
            raise

    async def _execute_sequential(self, workflow: Workflow) -> Dict[str, Any]:
        """串行执行

        按任务列表顺序依次执行。

        Args:
            workflow: 工作流对象

        Returns:
            Dict: 任务执行结果
        """
        results = {}

        for task_id, task in workflow.tasks.items():
            # 检查信号
            if await self._check_signal(workflow.id, WorkflowSignal.CANCEL):
                task.status = TaskStatus.CANCELLED
                logger.warning("workflow.cancelled", workflow_id=workflow.id)
                break

            # 等待暂停恢复
            await self._wait_for_resume(workflow.id)

            try:
                result = await self._execute_task(task)
                results[task_id] = result
            except Exception as e:
                results[task_id] = {"error": str(e)}
                raise WorkflowError(f"Task {task_id} failed: {e}")

        return results

    async def _execute_parallel(self, workflow: Workflow) -> Dict[str, Any]:
        """并行执行

        所有任务同时执行，无视依赖关系。

        Args:
            workflow: 工作流对象

        Returns:
            Dict: 任务执行结果
        """
        tasks = [
            self._execute_task_with_signal_check(workflow.id, task)
            for task in workflow.tasks.values()
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for task_id, result in zip(workflow.tasks.keys(), results_list):
            if isinstance(result, Exception):
                results[task_id] = {"error": str(result)}
            else:
                results[task_id] = result

        return results

    async def _execute_dag(self, workflow: Workflow) -> Dict[str, Any]:
        """DAG 执行 - 拓扑排序

        根据任务依赖关系进行拓扑排序，并行执行就绪任务。

        Args:
            workflow: 工作流对象

        Returns:
            Dict: 任务执行结果

        Raises:
            WorkflowError: 检测到循环依赖
        """
        completed: Set[str] = set()
        results: Dict[str, Any] = {}
        pending_tasks = set(workflow.tasks.keys())

        while pending_tasks:
            # 检查是否取消
            if await self._check_signal(workflow.id, WorkflowSignal.CANCEL):
                logger.warning("workflow.cancelled", workflow_id=workflow.id)
                for task_id in pending_tasks:
                    workflow.tasks[task_id].status = TaskStatus.CANCELLED
                break

            # 等待暂停恢复
            await self._wait_for_resume(workflow.id)

            # 找出可执行的任务（依赖已完成）
            ready = [
                workflow.tasks[tid]
                for tid in pending_tasks
                if workflow.tasks[tid].status == TaskStatus.PENDING
                and all(
                    dep in completed for dep in (workflow.tasks[tid].dependencies or [])
                )
            ]

            if not ready:
                # 检查是否有循环依赖
                if pending_tasks:
                    remaining = [workflow.tasks[tid] for tid in pending_tasks]
                    raise WorkflowError(f"Circular dependency detected: {remaining}")
                break

            # 并行执行就绪任务
            logger.debug(
                "workflow.executing_batch",
                workflow_id=workflow.id,
                ready_tasks=[t.id for t in ready],
            )

            batch_tasks = [
                self._execute_task_with_deps(task, workflow.tasks) for task in ready
            ]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)

            for task, result in zip(ready, batch_results):
                pending_tasks.discard(task.id)
                completed.add(task.id)

                if isinstance(result, Exception):
                    results[task.id] = {"error": str(result)}
                    task.status = TaskStatus.FAILED
                    task.error = str(result)
                    logger.error(
                        "workflow.task_failed",
                        workflow_id=workflow.id,
                        task_id=task.id,
                        error=str(result),
                    )
                else:
                    results[task.id] = result
                    task.result = result

        return results

    async def _execute_task_with_signal_check(
        self, workflow_id: str, task: Task
    ) -> Any:
        """执行单个任务（带信号检查）"""
        if await self._check_signal(workflow_id, WorkflowSignal.CANCEL):
            task.status = TaskStatus.CANCELLED
            raise WorkflowError(f"Workflow {workflow_id} was cancelled")

        await self._wait_for_resume(workflow_id)
        return await self._execute_task(task)

    async def _execute_task_with_deps(
        self, task: Task, all_tasks: Dict[str, Task]
    ) -> Any:
        """执行任务（注入依赖结果）"""
        # 注入依赖结果
        kwargs = dict(task.kwargs)
        if task.dependencies:
            dep_results = {
                dep: all_tasks[dep].result for dep in task.dependencies if dep in all_tasks
            }
            kwargs["dependencies"] = dep_results

        # 更新任务参数
        task.kwargs = kwargs
        return await self._execute_task(task)

    async def _execute_task(self, task: Task) -> Any:
        """执行单个任务

        Args:
            task: 任务对象

        Returns:
            Any: 任务执行结果

        Raises:
            Exception: 任务执行失败
        """
        async with self.semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()

            logger.info(
                "workflow.task_started",
                task_id=task.id,
                task_name=task.name,
            )

            try:
                # 执行（带超时）
                if asyncio.iscoroutinefunction(task.func):
                    result = await asyncio.wait_for(
                        task.func(*task.args, **task.kwargs),
                        timeout=task.timeout,
                    )
                else:
                    # 同步函数在线程池中执行
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, task.func, *task.args),
                        timeout=task.timeout,
                    )

                task.result = result
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()

                duration = (task.completed_at - task.started_at).total_seconds()
                logger.info(
                    "workflow.task_completed",
                    task_id=task.id,
                    task_name=task.name,
                    duration=duration,
                )

                return result

            except asyncio.TimeoutError:
                task.status = TaskStatus.FAILED
                task.error = f"Timeout after {task.timeout}s"
                task.completed_at = datetime.now()

                logger.error(
                    "workflow.task_timeout",
                    task_id=task.id,
                    task_name=task.name,
                    timeout=task.timeout,
                )

                # 重试逻辑
                if task.retry_count < task.retries:
                    task.retry_count += 1
                    logger.info(
                        "workflow.task_retry",
                        task_id=task.id,
                        retry_count=task.retry_count,
                        max_retries=task.retries,
                    )
                    await asyncio.sleep(0.5 * task.retry_count)  # 指数退避
                    return await self._execute_task(task)

                raise WorkflowError(f"Task {task.id} timed out after {task.timeout}s")

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.error = str(e)
                task.completed_at = datetime.now()

                logger.error(
                    "workflow.task_failed",
                    task_id=task.id,
                    task_name=task.name,
                    error=str(e),
                )

                # 重试逻辑
                if task.retry_count < task.retries:
                    task.retry_count += 1
                    logger.info(
                        "workflow.task_retry",
                        task_id=task.id,
                        retry_count=task.retry_count,
                        max_retries=task.retries,
                    )
                    await asyncio.sleep(0.5 * task.retry_count)
                    return await self._execute_task(task)

                raise

    async def _check_signal(self, workflow_id: str, signal: WorkflowSignal) -> bool:
        """检查信号"""
        async with self._lock:
            return self._signals.get(workflow_id) == signal

    async def _wait_for_resume(self, workflow_id: str) -> None:
        """等待恢复信号"""
        while True:
            async with self._lock:
                if self._signals.get(workflow_id) != WorkflowSignal.PAUSE:
                    break
            await asyncio.sleep(0.1)

    async def pause(self, workflow_id: str) -> None:
        """暂停工作流

        Args:
            workflow_id: 工作流 ID
        """
        async with self._lock:
            if workflow_id in self._workflows:
                self._signals[workflow_id] = WorkflowSignal.PAUSE
                self._workflows[workflow_id].status = WorkflowStatus.PAUSED

        logger.info("workflow.paused", workflow_id=workflow_id)

    async def resume(self, workflow_id: str) -> None:
        """恢复工作流

        Args:
            workflow_id: 工作流 ID
        """
        async with self._lock:
            if workflow_id in self._workflows:
                self._signals[workflow_id] = WorkflowSignal.RESUME
                if self._workflows[workflow_id].status == WorkflowStatus.PAUSED:
                    self._workflows[workflow_id].status = WorkflowStatus.RUNNING

        logger.info("workflow.resumed", workflow_id=workflow_id)

    async def cancel(self, workflow_id: str) -> None:
        """取消工作流

        Args:
            workflow_id: 工作流 ID
        """
        async with self._lock:
            if workflow_id in self._workflows:
                self._signals[workflow_id] = WorkflowSignal.CANCEL
                self._workflows[workflow_id].status = WorkflowStatus.CANCELLED

        logger.info("workflow.cancelled", workflow_id=workflow_id)

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """获取工作流状态

        Args:
            workflow_id: 工作流 ID

        Returns:
            Optional[Workflow]: 工作流对象
        """
        return self._workflows.get(workflow_id)

    def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowStatus]:
        """获取工作流状态

        Args:
            workflow_id: 工作流 ID

        Returns:
            Optional[WorkflowStatus]: 工作流状态
        """
        workflow = self._workflows.get(workflow_id)
        return workflow.status if workflow else None

    async def cleanup(self, workflow_id: Optional[str] = None) -> None:
        """清理工作流

        Args:
            workflow_id: 工作流 ID（可选，不指定则清理所有）
        """
        async with self._lock:
            if workflow_id:
                self._workflows.pop(workflow_id, None)
                self._signals.pop(workflow_id, None)
                logger.info("workflow.cleaned", workflow_id=workflow_id)
            else:
                self._workflows.clear()
                self._signals.clear()
                logger.info("workflow.all_cleaned")


# 便捷函数
def create_task(
    name: str,
    func: Callable[..., Any],
    dependencies: Optional[List[str]] = None,
    **kwargs: Any,
) -> Task:
    """创建任务的便捷函数

    Args:
        name: 任务名称
        func: 执行函数
        dependencies: 依赖任务 ID 列表
        **kwargs: 其他参数

    Returns:
        Task: 任务对象
    """
    return Task(
        id=str(uuid4()),
        name=name,
        func=func,
        dependencies=dependencies or [],
        **kwargs,
    )
